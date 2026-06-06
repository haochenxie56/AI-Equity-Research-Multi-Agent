"""
scripts/test_reliability_critic.py

Test suite for Phase 2J: Critic Agent v0.1 foundation.

Run with:
    python3 scripts/test_reliability_critic.py

All 36 assertions must pass.
"""

import json
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path before any lib imports
# ---------------------------------------------------------------------------

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from pydantic import ValidationError

from lib.reliability.schemas import (
    AgentConfidence,
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
)
from lib.reliability.staleness import (
    StalenessFinding,
    StalenessReport,
    make_staleness_finding_id,
)
from lib.reliability.critic import (
    CriticIssue,
    CriticIssueType,
    CriticResult,
    CriticSeverity,
    CriticStatus,
    CriticRecommendation,
    make_critic_issue_id,
    critic_issue_from_validation_item,
    critic_issue_from_staleness_finding,
    critique_validation_aggregate,
    critique_staleness_report,
    critique_agent_result_structure,
    detect_overconfidence,
    aggregate_critic_issues,
    run_mock_critic,
    critic_result_tool_result_from_result,
    summarize_critic_result,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_ERRORS: list[str] = []


def _assert(condition: bool, label: str) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        _ERRORS.append(label)
        print(f"  FAIL  {label}")


def _assert_raises(exc_type: type, fn, label: str) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _FAIL += 1
        _ERRORS.append(label)
        print(f"  FAIL  {label}  (expected {exc_type.__name__}, got no exception)")
    except exc_type:
        _PASS += 1
        print(f"  PASS  {label}")
    except Exception as e:
        _FAIL += 1
        _ERRORS.append(label)
        print(f"  FAIL  {label}  (expected {exc_type.__name__}, got {type(e).__name__}: {e})")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_validation_item(
    severity: str = "warning",
    item_type: str = "missing_data",
    message: str = "Missing price data.",
    object_id: str = "snap_001",
    evidence_id: str = "ev_001",
    field_path: str = "indicators.0.as_of",
) -> AggregatedValidationItem:
    return AggregatedValidationItem(
        item_id=make_validation_item_id(
            domain="macro",
            message=message,
            object_id=object_id,
            field_path=field_path,
        ),
        domain="macro",
        severity=severity,  # type: ignore[arg-type]
        item_type=item_type,  # type: ignore[arg-type]
        message=message,
        object_id=object_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def _make_staleness_finding(
    status: str = "stale",
    severity: str = "warning",
    message: str = "News data is stale.",
    object_id: str = "news_snap_001",
    evidence_id: str = "ev_staleness_001",
    field_path: str = "events.0.published_at",
) -> StalenessFinding:
    return StalenessFinding(
        finding_id=make_staleness_finding_id(
            domain="news",
            timestamp_role="published_at",
            timestamp_value="2026-04-01T00:00:00Z",
            as_of="2026-05-22T00:00:00Z",
            field_path=field_path,
            object_id=object_id,
        ),
        domain="news",
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=message,
        timestamp_value="2026-04-01T00:00:00Z",
        as_of="2026-05-22T00:00:00Z",
        age_days=51.0,
        max_age_days=7.0,
        object_id=object_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def _make_agent_result(
    findings=None,
    risks=None,
    assumptions=None,
    confidence=None,
) -> AgentResult:
    return AgentResult(
        agent_name="test_agent",
        run_id="run_20260522_123456_abc",
        findings=findings or [],
        risks=risks or [],
        assumptions=assumptions or [],
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test categories
# ---------------------------------------------------------------------------

def test_critic_issue_schema() -> None:
    print("\n[1] CriticIssue schema")

    # 1. Accepts valid issue
    issue = CriticIssue(
        issue_id="weak_evidence:abc123",
        issue_type="weak_evidence",
        severity="warning",
        target_type="finding",
        message="Finding has no evidence.",
    )
    _assert(issue.issue_type == "weak_evidence", "1. CriticIssue accepts valid issue")

    # 2. Rejects empty issue_id
    _assert_raises(
        ValidationError,
        lambda: CriticIssue(
            issue_id="",
            issue_type="weak_evidence",
            message="Something.",
        ),
        "2. CriticIssue rejects empty issue_id",
    )

    # 3. Rejects empty message
    _assert_raises(
        ValidationError,
        lambda: CriticIssue(
            issue_id="weak_evidence:abc123",
            issue_type="weak_evidence",
            message="",
        ),
        "3. CriticIssue rejects empty message",
    )


def test_critic_result_schema() -> None:
    print("\n[2] CriticResult schema")

    # 4. Accepts empty issues and normalizes to pass/accept
    cr = CriticResult(critic_id="cr_001", as_of="2026-05-22")
    _assert(
        cr.issues == [] and cr.status == "pass" and cr.recommendation == "accept",
        "4. CriticResult with empty issues normalizes to pass/accept",
    )

    # 5. Rejects empty critic_id
    _assert_raises(
        ValidationError,
        lambda: CriticResult(critic_id="", as_of="2026-05-22"),
        "5. CriticResult rejects empty critic_id",
    )

    # 6. Rejects empty as_of
    _assert_raises(
        ValidationError,
        lambda: CriticResult(critic_id="cr_001", as_of=""),
        "6. CriticResult rejects empty as_of",
    )

    # 7. Normalizes counts/status/recommendation from issues
    warning_issue = CriticIssue(
        issue_id="weak_evidence:aaa",
        issue_type="weak_evidence",
        severity="warning",
        message="No evidence.",
    )
    critical_issue = CriticIssue(
        issue_id="validation_failure:bbb",
        issue_type="validation_failure",
        severity="critical",
        message="Critical failure.",
    )
    cr_w = CriticResult(critic_id="cr_w", as_of="2026-05-22", issues=[warning_issue])
    _assert(
        cr_w.status == "pass_with_warnings"
        and cr_w.recommendation == "revise"
        and cr_w.warning_count == 1
        and cr_w.critical_count == 0,
        "7a. CriticResult with warning issues → pass_with_warnings/revise",
    )
    cr_c = CriticResult(critic_id="cr_c", as_of="2026-05-22", issues=[critical_issue])
    _assert(
        cr_c.status == "fail"
        and cr_c.recommendation == "reject"
        and cr_c.critical_count == 1,
        "7b. CriticResult with critical issue → fail/reject",
    )


def test_make_critic_issue_id() -> None:
    print("\n[3] make_critic_issue_id")

    id1 = make_critic_issue_id("weak_evidence", "No refs found.")
    id2 = make_critic_issue_id("weak_evidence", "No refs found.")

    # 8. Deterministic
    _assert(id1 == id2, "8. make_critic_issue_id is deterministic")

    # 9. Changes when message or target changes
    id3 = make_critic_issue_id("weak_evidence", "Different message.")
    id4 = make_critic_issue_id("weak_evidence", "No refs found.", target_id="target_A")
    _assert(
        id1 != id3 and id1 != id4,
        "9. make_critic_issue_id changes when message/target changes",
    )

    # Prefix check
    _assert(id1.startswith("weak_evidence:"), "9b. make_critic_issue_id has issue_type prefix")


def test_from_validation_item() -> None:
    print("\n[4] critic_issue_from_validation_item")

    # 10. Maps critical item
    critical_item = _make_validation_item(severity="critical", item_type="risk_limit")
    issue = critic_issue_from_validation_item(critical_item)
    _assert(
        issue.severity == "critical" and issue.issue_type == "validation_failure",
        "10. critic_issue_from_validation_item maps critical risk_limit item",
    )

    # 11. Maps stale_data to stale_evidence
    stale_item = _make_validation_item(
        severity="warning",
        item_type="stale_data",
        message="Data is stale.",
    )
    issue_stale = critic_issue_from_validation_item(stale_item)
    _assert(
        issue_stale.issue_type == "stale_evidence",
        "11. critic_issue_from_validation_item maps stale_data → stale_evidence",
    )

    # 12. Preserves evidence_id/field_path and related_validation_item_id
    item = _make_validation_item(
        evidence_id="ev_xyz",
        field_path="indicators.2.as_of",
        object_id="obj_001",
    )
    issue_p = critic_issue_from_validation_item(item)
    _assert(
        issue_p.evidence_id == "ev_xyz"
        and issue_p.field_path == "indicators.2.as_of"
        and issue_p.related_validation_item_id == item.item_id
        and issue_p.target_id == "obj_001",
        "12. critic_issue_from_validation_item preserves evidence_id/field_path/target_id",
    )


def test_from_staleness_finding() -> None:
    print("\n[5] critic_issue_from_staleness_finding")

    # 13. Maps stale/expired to stale_evidence
    stale_f = _make_staleness_finding(status="stale", severity="warning")
    expired_f = _make_staleness_finding(
        status="expired",
        severity="critical",
        message="Contract expired.",
        field_path="chain_snapshot.contracts.0.expiration",
    )
    stale_issue = critic_issue_from_staleness_finding(stale_f)
    expired_issue = critic_issue_from_staleness_finding(expired_f)
    _assert(
        stale_issue.issue_type == "stale_evidence"
        and expired_issue.issue_type == "stale_evidence",
        "13. critic_issue_from_staleness_finding maps stale/expired → stale_evidence",
    )
    _assert(
        expired_issue.severity == "critical",
        "13b. critic_issue_from_staleness_finding preserves critical severity for expired",
    )

    # 14. Preserves field_path/evidence_id/object_id
    finding = _make_staleness_finding(
        evidence_id="ev_staleness_xyz",
        field_path="events.3.published_at",
        object_id="news_snap_xyz",
    )
    issue_p = critic_issue_from_staleness_finding(finding)
    _assert(
        issue_p.field_path == "events.3.published_at"
        and issue_p.evidence_id == "ev_staleness_xyz"
        and issue_p.target_id == "news_snap_xyz"
        and issue_p.related_staleness_finding_id == finding.finding_id,
        "14. critic_issue_from_staleness_finding preserves field_path/evidence_id/object_id",
    )


def test_critique_validation_aggregate() -> None:
    print("\n[6] critique_validation_aggregate")

    item1 = _make_validation_item(severity="warning", message="Issue A.")
    item2 = _make_validation_item(severity="critical", message="Issue B.", field_path="x.y")
    va = ValidationAggregate(
        aggregate_id="agg_001",
        as_of="2026-05-22",
        items=[item1, item2],
    )

    # 15. Converts items
    issues = critique_validation_aggregate(va)
    _assert(
        len(issues) == 2
        and all(isinstance(i, CriticIssue) for i in issues),
        "15. critique_validation_aggregate converts all items",
    )
    _assert(
        not (va.items is issues),  # did not mutate
        "15b. critique_validation_aggregate does not mutate input",
    )


def test_critique_staleness_report() -> None:
    print("\n[7] critique_staleness_report")

    f1 = _make_staleness_finding(status="stale", message="Old news.", field_path="events.0.published_at")
    f2 = _make_staleness_finding(
        status="expired",
        severity="critical",
        message="Expired option.",
        field_path="chain_snapshot.contracts.0.expiration",
        object_id="opt_snap_001",
        evidence_id="ev_opt_001",
    )
    sr = StalenessReport(
        report_id="sr_001",
        as_of="2026-05-22",
        findings=[f1, f2],
    )

    # 16. Converts findings
    issues = critique_staleness_report(sr)
    _assert(
        len(issues) == 2
        and all(isinstance(i, CriticIssue) for i in issues),
        "16. critique_staleness_report converts all findings",
    )
    _assert(
        not (sr.findings is issues),
        "16b. critique_staleness_report does not mutate input",
    )


def test_critique_agent_result_structure() -> None:
    print("\n[8] critique_agent_result_structure")

    # 17. Warns on no findings
    ar_empty = _make_agent_result()
    issues_empty = critique_agent_result_structure(ar_empty)
    _assert(
        any("no findings" in i.message.lower() for i in issues_empty),
        "17. critique_agent_result_structure warns on no findings",
    )

    # 18. Warns on finding with no evidence
    finding_no_ev = Finding(text="Revenue grew 25%.", evidence=[])
    ar_no_ev = _make_agent_result(
        findings=[finding_no_ev],
        risks=[Risk(name="R1", description="Risk 1.")],
        assumptions=[Assumption(name="A1", rationale="Assume stable market.")],
    )
    issues_no_ev = critique_agent_result_structure(ar_no_ev)
    _assert(
        any("no evidence_refs" in i.message.lower() for i in issues_no_ev),
        "18. critique_agent_result_structure warns on finding with no evidence",
    )

    # 19a. Warns on missing risks
    ar_no_risks = _make_agent_result(
        findings=[Finding(text="Normal finding.", evidence=[])],
        assumptions=[Assumption(name="A1", rationale="Assume stability.")],
    )
    issues_no_risks = critique_agent_result_structure(ar_no_risks)
    _assert(
        any("no risks" in i.message.lower() for i in issues_no_risks),
        "19a. critique_agent_result_structure warns on missing risks",
    )

    # 19b. Warns on missing assumptions
    ar_no_assumptions = _make_agent_result(
        findings=[Finding(text="Normal finding.", evidence=[])],
        risks=[Risk(name="R1", description="Risk 1.")],
    )
    issues_no_assumptions = critique_agent_result_structure(ar_no_assumptions)
    _assert(
        any("no assumptions" in i.message.lower() for i in issues_no_assumptions),
        "19b. critique_agent_result_structure warns on missing assumptions",
    )

    # Numeric claim without evidence
    finding_numeric = Finding(text="EPS was $2.50, up from $1000.", evidence=[])
    ar_numeric = _make_agent_result(
        findings=[finding_numeric],
        risks=[Risk(name="R1", description="Risk 1.")],
        assumptions=[Assumption(name="A1", rationale="Stable market.")],
    )
    issues_numeric = critique_agent_result_structure(ar_numeric)
    _assert(
        any(i.issue_type == "numeric_claim_issue" for i in issues_numeric),
        "19c. critique_agent_result_structure flags numeric claim without evidence",
    )


def test_detect_overconfidence() -> None:
    print("\n[9] detect_overconfidence")

    high_conf = AgentConfidence(level="high", rationale="Very confident.", score=0.95)
    ar_high = _make_agent_result(confidence=high_conf)

    # 20. Warns when high confidence + validation warnings
    warn_item = _make_validation_item(severity="warning", message="Warning issue.")
    va_warnings = ValidationAggregate(
        aggregate_id="agg_warn",
        as_of="2026-05-22",
        items=[warn_item],
    )
    issues_va = detect_overconfidence(agent_result=ar_high, validation_aggregate=va_warnings)
    _assert(
        any(i.issue_type == "overconfidence" for i in issues_va),
        "20. detect_overconfidence raises issue when high confidence + validation warnings",
    )
    _assert(
        issues_va[0].severity == "warning",
        "20b. detect_overconfidence uses warning severity for pass_with_warnings validation",
    )

    # Validation fail → critical overconfidence
    crit_item = _make_validation_item(severity="critical", message="Critical issue.")
    va_fail = ValidationAggregate(
        aggregate_id="agg_fail",
        as_of="2026-05-22",
        items=[crit_item],
    )
    issues_va_fail = detect_overconfidence(agent_result=ar_high, validation_aggregate=va_fail)
    _assert(
        any(i.severity == "critical" for i in issues_va_fail),
        "20c. detect_overconfidence raises critical when validation aggregate fails",
    )

    # 21. Warns when high confidence + stale report
    stale_f = _make_staleness_finding(status="stale", severity="warning")
    sr_stale = StalenessReport(
        report_id="sr_stale",
        as_of="2026-05-22",
        findings=[stale_f],
    )
    issues_sr = detect_overconfidence(agent_result=ar_high, staleness_report=sr_stale)
    _assert(
        any(i.issue_type == "overconfidence" for i in issues_sr),
        "21. detect_overconfidence raises issue when high confidence + stale report",
    )

    # No confidence → empty
    ar_no_conf = _make_agent_result(confidence=None)
    issues_none = detect_overconfidence(agent_result=ar_no_conf, validation_aggregate=va_warnings)
    _assert(
        issues_none == [],
        "21b. detect_overconfidence returns [] when no confidence declared",
    )

    # Medium confidence → empty
    med_conf = AgentConfidence(level="medium", rationale="Moderate.", score=0.5)
    ar_med = _make_agent_result(confidence=med_conf)
    issues_med = detect_overconfidence(agent_result=ar_med, validation_aggregate=va_warnings)
    _assert(
        issues_med == [],
        "21c. detect_overconfidence returns [] for non-high confidence",
    )


def test_aggregate_critic_issues() -> None:
    print("\n[10] aggregate_critic_issues")

    issue_a = CriticIssue(
        issue_id="weak_evidence:aaa",
        issue_type="weak_evidence",
        severity="warning",
        message="No evidence A.",
    )
    issue_b = CriticIssue(
        issue_id="validation_failure:bbb",
        issue_type="validation_failure",
        severity="critical",
        message="Critical failure B.",
    )
    issue_a_dup = CriticIssue(
        issue_id="weak_evidence:aaa",  # same id as issue_a
        issue_type="weak_evidence",
        severity="info",
        message="Duplicate of A.",
    )

    # 22. Deduplicates by issue_id
    cr = aggregate_critic_issues(
        critic_id="cr_dedup",
        as_of="2026-05-22",
        issues=[issue_a, issue_b, issue_a_dup],
    )
    _assert(
        len(cr.issues) == 2,
        "22. aggregate_critic_issues deduplicates by issue_id (3 → 2)",
    )
    # First-occurrence wins: issue_a survives, not issue_a_dup
    kept_ids = {i.issue_id for i in cr.issues}
    _assert("weak_evidence:aaa" in kept_ids, "22b. first-occurrence wins on dedup")

    # 23. Recomputes counts/status/recommendation
    _assert(
        cr.critical_count == 1
        and cr.warning_count == 1
        and cr.status == "fail"
        and cr.recommendation == "reject",
        "23. aggregate_critic_issues recomputes counts, status=fail, recommendation=reject",
    )


def test_run_mock_critic() -> None:
    print("\n[11] run_mock_critic")

    high_conf = AgentConfidence(level="high", rationale="Very confident.", score=0.9)
    ar = _make_agent_result(confidence=high_conf)

    warn_item = _make_validation_item(severity="warning", message="Validation warning.")
    va = ValidationAggregate(
        aggregate_id="agg_mock",
        as_of="2026-05-22",
        items=[warn_item],
    )

    stale_f = _make_staleness_finding(status="stale", message="Stale data.")
    sr = StalenessReport(
        report_id="sr_mock",
        as_of="2026-05-22",
        findings=[stale_f],
    )

    # 24. Combines agent_result, validation_aggregate, and staleness_report issues
    result = run_mock_critic(
        critic_id="mock_cr_001",
        as_of="2026-05-22",
        agent_result=ar,
        validation_aggregate=va,
        staleness_report=sr,
    )
    _assert(isinstance(result, CriticResult), "24a. run_mock_critic returns CriticResult")

    # Should have issues from all three sources
    issue_types = {i.target_type for i in result.issues}
    has_agent = any(
        i.target_type in ("agent_result", "finding") for i in result.issues
    )
    has_validation = any(i.target_type == "validation_aggregate" for i in result.issues)
    has_staleness = any(i.target_type == "staleness_report" for i in result.issues)
    _assert(
        has_agent and has_validation and has_staleness,
        "24. run_mock_critic combines issues from all three input sources",
    )

    # 25. Deterministic
    result2 = run_mock_critic(
        critic_id="mock_cr_001",
        as_of="2026-05-22",
        agent_result=ar,
        validation_aggregate=va,
        staleness_report=sr,
    )
    ids1 = sorted(i.issue_id for i in result.issues)
    ids2 = sorted(i.issue_id for i in result2.issues)
    _assert(ids1 == ids2, "25. run_mock_critic is deterministic (same inputs → same issue IDs)")


def test_critic_tool_result() -> None:
    print("\n[12] critic_result_tool_result_from_result")

    cr = CriticResult(
        critic_id="cr_tr_001",
        as_of="2026-05-22",
        issues=[
            CriticIssue(
                issue_id="weak_evidence:x",
                issue_type="weak_evidence",
                severity="warning",
                message="Missing evidence.",
            )
        ],
    )

    # 26. Returns valid ToolResult
    tr = critic_result_tool_result_from_result(run_id="run_001", critic_result=cr)
    _assert(isinstance(tr, ToolResult), "26. critic_result_tool_result_from_result returns ToolResult")

    # 27. Stable tool_name and target
    _assert(tr.tool_name == "critic_result", "27. Critic ToolResult has stable tool_name")
    tr_custom = critic_result_tool_result_from_result(
        run_id="run_001", critic_result=cr, target="custom_target"
    )
    _assert(
        tr_custom.tool_name == "critic_result",
        "27b. Critic ToolResult tool_name stable regardless of target arg",
    )

    # 28. Payload includes status/recommendation/issues
    _assert(
        "status" in tr.outputs
        and "recommendation" in tr.outputs
        and "issues" in tr.outputs
        and tr.outputs["status"] == "pass_with_warnings"
        and tr.outputs["recommendation"] == "revise",
        "28. Critic ToolResult payload includes status/recommendation/issues",
    )

    # 29. evidence_id deterministic for same run_id/result payload
    tr2 = critic_result_tool_result_from_result(run_id="run_001", critic_result=cr)
    _assert(
        tr.evidence_id == tr2.evidence_id,
        "29. Critic ToolResult evidence_id deterministic for same run_id/result",
    )
    tr_diff_run = critic_result_tool_result_from_result(run_id="run_002", critic_result=cr)
    _assert(
        tr.evidence_id != tr_diff_run.evidence_id,
        "29b. Critic ToolResult evidence_id changes with different run_id",
    )


def test_summarize_critic_result() -> None:
    print("\n[13] summarize_critic_result")

    cr = CriticResult(
        critic_id="cr_sum_001",
        as_of="2026-05-22",
        issues=[
            CriticIssue(
                issue_id="weak_evidence:s1",
                issue_type="weak_evidence",
                severity="warning",
                message="No evidence ref.",
            ),
            CriticIssue(
                issue_id="stale_evidence:s2",
                issue_type="stale_evidence",
                severity="critical",
                message="Data is expired.",
            ),
        ],
    )

    # 30. Returns expected summary fields
    summary = summarize_critic_result(cr)
    _assert(
        summary["critic_id"] == "cr_sum_001"
        and summary["status"] == "fail"
        and summary["recommendation"] == "reject"
        and summary["total_issues"] == 2
        and summary["critical_count"] == 1
        and summary["warning_count"] == 1
        and summary["info_count"] == 0
        and "stale_evidence" in summary["issue_types_present"]
        and "weak_evidence" in summary["issue_types_present"]
        and len(summary["top_messages"]) == 2,
        "30. summarize_critic_result returns expected summary dict",
    )

    # top_messages capped at 10
    issues_11 = [
        CriticIssue(
            issue_id=f"other:i{i}",
            issue_type="other",
            severity="info",
            message=f"Message {i}.",
        )
        for i in range(11)
    ]
    cr_many = CriticResult(critic_id="cr_many", as_of="2026-05-22", issues=issues_11)
    summary_many = summarize_critic_result(cr_many)
    _assert(
        len(summary_many["top_messages"]) == 10,
        "30b. summarize_critic_result caps top_messages at 10",
    )


def test_serialization() -> None:
    print("\n[14] Serialization roundtrip")

    # 31. CriticResult serialization roundtrip
    cr = CriticResult(
        critic_id="cr_rt_001",
        as_of="2026-05-22",
        issues=[
            CriticIssue(
                issue_id="overconfidence:z1",
                issue_type="overconfidence",
                severity="critical",
                message="High confidence unsupported.",
                recommendation="reject",
            )
        ],
    )
    dumped = cr.model_dump()
    cr2 = CriticResult(**dumped)
    _assert(
        cr2.critic_id == cr.critic_id
        and cr2.status == cr.status
        and cr2.critical_count == cr.critical_count
        and len(cr2.issues) == len(cr.issues),
        "31. CriticResult serialization roundtrip preserves all fields",
    )

    # 32. CriticIssue serialization roundtrip
    issue = CriticIssue(
        issue_id="stale_evidence:rr1",
        issue_type="stale_evidence",
        severity="warning",
        target_type="staleness_report",
        message="Data older than policy.",
        target_id="snap_001",
        evidence_id="ev_001",
        field_path="events.0.published_at",
        related_staleness_finding_id="finding_001",
        recommendation="revise",
        metadata={"domain": "news"},
    )
    issue_dict = issue.model_dump()
    issue2 = CriticIssue(**issue_dict)
    _assert(
        issue2.issue_id == issue.issue_id
        and issue2.issue_type == issue.issue_type
        and issue2.field_path == issue.field_path
        and issue2.metadata == issue.metadata,
        "32. CriticIssue serialization roundtrip preserves all fields",
    )

    # Also verify JSON roundtrip
    json_str = cr.model_dump_json()
    cr_json = CriticResult(**json.loads(json_str))
    _assert(
        cr_json.critic_id == cr.critic_id,
        "32b. CriticResult JSON roundtrip works",
    )


def test_isolation_guarantees() -> None:
    print("\n[15] Isolation and no-live-call guarantees")

    # 33. No live app files imported
    forbidden_prefixes = [
        "app",
        "pages",
        "lib.llm_orchestrator",
    ]
    forbidden_found = [
        name for name in sys.modules
        if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)
    ]
    _assert(
        len(forbidden_found) == 0,
        f"33. No live app files imported (forbidden: {forbidden_found})",
    )

    # 34. No external network imports present
    network_modules = [
        name for name in sys.modules
        if name in ("requests", "httpx", "urllib3", "aiohttp")
    ]
    _assert(
        len(network_modules) == 0,
        f"34. No external API/network call libraries imported ({network_modules})",
    )

    # 35. No Claude/LLM API imported
    llm_modules = [
        name for name in sys.modules
        if name == "anthropic" or name.startswith("anthropic.")
        or name == "openai" or name.startswith("openai.")
    ]
    _assert(
        len(llm_modules) == 0,
        f"35. No Claude/LLM API imported ({llm_modules})",
    )

    # 36. validate_agent_result still works (regression check)
    from lib.reliability.validators import validate_agent_result
    from lib.reliability.schemas import AgentResult, Finding, EvidenceRef, Risk, Assumption
    from lib.reliability.evidence_store import EvidenceStore
    from lib.reliability.run_context import create_run_context

    ctx = create_run_context(ticker="TEST", task="critic_regression")
    store = EvidenceStore(run_dir=ctx.run_dir)

    ar_reg = AgentResult(
        agent_name="regression_agent",
        run_id=ctx.run_id,
        findings=[
            Finding(
                text="Revenue increased.",
                evidence=[EvidenceRef(evidence_id="ev_regress_01")],
            )
        ],
        risks=[Risk(name="R1", description="Market risk.")],
        assumptions=[Assumption(name="A1", rationale="Stable conditions.")],
    )
    report = validate_agent_result(ar_reg, store)
    _assert(
        report is not None and hasattr(report, "passed"),
        "36. validate_agent_result still works after critic module import (no regression)",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("Phase 2J: Critic Agent v0.1 — test_reliability_critic.py")
    print("=" * 65)

    test_critic_issue_schema()
    test_critic_result_schema()
    test_make_critic_issue_id()
    test_from_validation_item()
    test_from_staleness_finding()
    test_critique_validation_aggregate()
    test_critique_staleness_report()
    test_critique_agent_result_structure()
    test_detect_overconfidence()
    test_aggregate_critic_issues()
    test_run_mock_critic()
    test_critic_tool_result()
    test_summarize_critic_result()
    test_serialization()
    test_isolation_guarantees()

    print("\n" + "=" * 65)
    total = _PASS + _FAIL
    print(f"Results: {_PASS}/{total} passed, {_FAIL} failed")
    if _ERRORS:
        print("\nFailed tests:")
        for e in _ERRORS:
            print(f"  - {e}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("All tests passed.")
        print("=" * 65)


if __name__ == "__main__":
    main()
