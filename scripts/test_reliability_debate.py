"""
scripts/test_reliability_debate.py

Phase 3D: Tests for the Debate by Horizon Skeleton.

Run with:
    python3 scripts/test_reliability_debate.py

Coverage: 54 assertions spanning schema validation, ID helpers, evidence
extraction, issue conversion, position/round builders, run_debate_by_horizon,
ToolResult wrapper, summarisation, serialisation round-trip, no-live-import
checks, and Phase 3B HorizonSynthesisReport field-name integration regression
tests (card.horizon / supporting_evidence_ids contract).
"""

import sys
import os

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback
from datetime import datetime, timezone
from typing import Any

# ── Imports from the module under test ──────────────────────────────────────
from lib.reliability.debate import (
    DebateClaim,
    DebateInputBundle,
    DebateIssue,
    DebatePosition,
    DebateReport,
    DebateRound,
    _get_horizon_synthesis_card,
    build_bear_position,
    build_bull_position,
    build_debate_round,
    build_risk_position,
    debate_report_tool_result_from_report,
    extract_debate_evidence_ids,
    issue_from_critic_issue_for_debate,
    issue_from_staleness_finding_for_debate,
    issue_from_validation_item_for_debate,
    make_debate_id,
    make_debate_issue_id,
    run_debate_by_horizon,
    summarize_debate_report,
)

# ── Phase 3B types for integration regression tests ──────────────────────────
from lib.reliability.horizon_synthesis import (
    HorizonEvidenceSummary,
    HorizonSynthesisCard,
    HorizonSynthesisReport,
)

# ── Supporting types ─────────────────────────────────────────────────────────
from lib.reliability.schemas import AgentResult, EvidenceRef, Finding, Risk, ToolResult
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
    make_validation_item_id,
)
from lib.reliability.staleness import StalenessFinding, StalenessReport
from lib.reliability.critic import CriticIssue, CriticResult, make_critic_issue_id


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0


def ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  PASS  {name}")


def fail(name: str, exc: Exception) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  FAIL  {name}: {exc}")
    traceback.print_exc()


def expect_raises(name: str, exc_type: type, fn) -> None:
    try:
        fn()
        global _FAIL
        _FAIL += 1
        print(f"  FAIL  {name}: expected {exc_type.__name__} but no exception raised")
    except exc_type:
        ok(name)
    except Exception as e:
        fail(name, e)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_tool_result(run_id: str = "run-1", evidence_id: str = "eid-1") -> ToolResult:
    return ToolResult(
        evidence_id=evidence_id,
        tool_name="test_tool",
        run_id=run_id,
        inputs={},
        outputs={"value": 1},
    )


def _make_validation_item(
    item_type: str = "stale_data",
    severity: str = "warning",
    evidence_id: str = "eid-v1",
    field_path: str = "data.price",
    object_id: str = "obj-1",
) -> AggregatedValidationItem:
    msg = f"Validation item of type {item_type}"
    item_id = make_validation_item_id(
        domain="macro",
        message=msg,
        object_id=object_id,
    )
    return AggregatedValidationItem(
        item_id=item_id,
        domain="macro",
        item_type=item_type,
        severity=severity,
        message=msg,
        object_id=object_id,
        field_path=field_path,
        evidence_id=evidence_id,
    )


def _make_staleness_finding(
    status: str = "stale",
    severity: str = "warning",
    evidence_id: str = "eid-s1",
    field_path: str = "data.timestamp",
    object_id: str = "obj-s1",
) -> StalenessFinding:
    from lib.reliability.staleness import make_staleness_finding_id
    msg = f"Staleness finding: status={status}"
    now = _utcnow()
    fid = make_staleness_finding_id(
        domain="macro",
        timestamp_role="fetched_at",
        timestamp_value=None,
        as_of=now,
        source_name=field_path,
    )
    return StalenessFinding(
        finding_id=fid,
        domain="macro",
        status=status,
        severity=severity,
        message=msg,
        as_of=now,
        object_id=object_id,
        field_path=field_path,
        evidence_id=evidence_id,
    )


def _make_critic_issue(
    issue_type: str = "missing_risk",
    severity: str = "warning",
    evidence_id: str = "eid-c1",
    field_path: str = "risks",
    target_id: str = "agent-1",
) -> CriticIssue:
    msg = f"Critic issue of type {issue_type}"
    iid = make_critic_issue_id(
        issue_type=issue_type,
        message=msg,
        target_id=target_id,
        evidence_id=evidence_id,
    )
    return CriticIssue(
        issue_id=iid,
        issue_type=issue_type,
        severity=severity,
        message=msg,
        target_id=target_id,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def _make_bundle(
    bundle_id: str = "bundle-1",
    ticker: str = "AAPL",
    tool_results=None,
    validation_aggregate=None,
    staleness_report=None,
    critic_result=None,
) -> DebateInputBundle:
    return DebateInputBundle(
        bundle_id=bundle_id,
        as_of="2026-01-01",
        ticker=ticker,
        tool_results=tool_results or [],
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
        critic_result=critic_result,
    )


# ---------------------------------------------------------------------------
# 1. DebateIssue accepts valid issue
# ---------------------------------------------------------------------------
try:
    issue = DebateIssue(
        issue_id="issue-1",
        issue_type="stale_evidence",
        message="Stale price data",
        horizon="short_term",
        role="risk",
    )
    assert issue.issue_id == "issue-1"
    assert issue.issue_type == "stale_evidence"
    assert issue.severity == "warning"
    ok("1. DebateIssue accepts valid issue")
except Exception as e:
    fail("1. DebateIssue accepts valid issue", e)

# ---------------------------------------------------------------------------
# 2. DebateIssue rejects empty issue_id
# ---------------------------------------------------------------------------
expect_raises(
    "2. DebateIssue rejects empty issue_id",
    Exception,
    lambda: DebateIssue(issue_id="", issue_type="other", message="msg"),
)

# ---------------------------------------------------------------------------
# 3. DebateIssue rejects empty message
# ---------------------------------------------------------------------------
expect_raises(
    "3. DebateIssue rejects empty message",
    Exception,
    lambda: DebateIssue(issue_id="i-1", issue_type="other", message=""),
)

# ---------------------------------------------------------------------------
# 4. DebateClaim accepts valid claim
# ---------------------------------------------------------------------------
try:
    claim = DebateClaim(
        claim_id="claim-1",
        claim_type="thesis",
        role="bull",
        horizon="short_term",
        text="The company shows strong growth prospects.",
        evidence_ids=["eid-1"],
        confidence="low",
    )
    assert claim.claim_id == "claim-1"
    assert claim.role == "bull"
    ok("4. DebateClaim accepts valid claim")
except Exception as e:
    fail("4. DebateClaim accepts valid claim", e)

# ---------------------------------------------------------------------------
# 5. DebateClaim rejects empty claim_id
# ---------------------------------------------------------------------------
expect_raises(
    "5. DebateClaim rejects empty claim_id",
    Exception,
    lambda: DebateClaim(
        claim_id="",
        claim_type="thesis",
        role="bull",
        horizon="short_term",
        text="text",
    ),
)

# ---------------------------------------------------------------------------
# 6. DebateClaim rejects empty text
# ---------------------------------------------------------------------------
expect_raises(
    "6. DebateClaim rejects empty text",
    Exception,
    lambda: DebateClaim(
        claim_id="c-1",
        claim_type="thesis",
        role="bull",
        horizon="short_term",
        text="",
    ),
)

# ---------------------------------------------------------------------------
# 7. DebatePosition accepts valid position
# ---------------------------------------------------------------------------
try:
    claim = DebateClaim(
        claim_id="claim-1",
        claim_type="thesis",
        role="bull",
        horizon="short_term",
        text="[MOCK] Bull thesis.",
    )
    pos = DebatePosition(
        position_id="pos-1",
        role="bull",
        horizon="short_term",
        summary="Bull position summary.",
        claims=[claim],
        evidence_ids=["eid-1"],
    )
    assert pos.position_id == "pos-1"
    assert pos.role == "bull"
    ok("7. DebatePosition accepts valid position")
except Exception as e:
    fail("7. DebatePosition accepts valid position", e)

# ---------------------------------------------------------------------------
# 8. DebatePosition rejects empty position_id
# ---------------------------------------------------------------------------
expect_raises(
    "8. DebatePosition rejects empty position_id",
    Exception,
    lambda: DebatePosition(
        position_id="",
        role="bull",
        horizon="short_term",
        summary="Summary",
    ),
)

# ---------------------------------------------------------------------------
# 9. DebatePosition rejects empty summary
# ---------------------------------------------------------------------------
expect_raises(
    "9. DebatePosition rejects empty summary",
    Exception,
    lambda: DebatePosition(
        position_id="pos-1",
        role="bull",
        horizon="short_term",
        summary="",
    ),
)

# ---------------------------------------------------------------------------
# 10. DebateRound accepts valid round
# ---------------------------------------------------------------------------
try:
    bull_pos = DebatePosition(
        position_id="pos-bull-1",
        role="bull",
        horizon="short_term",
        summary="Bull summary.",
        evidence_ids=["eid-1"],
    )
    rnd = DebateRound(
        round_id="round-1",
        horizon="short_term",
        bull_position=bull_pos,
    )
    assert rnd.round_id == "round-1"
    assert rnd.horizon == "short_term"
    # Status normalized (has evidence → not insufficient_evidence)
    assert rnd.status in ("pass", "pass_with_warnings")
    ok("10. DebateRound accepts valid round")
except Exception as e:
    fail("10. DebateRound accepts valid round", e)

# ---------------------------------------------------------------------------
# 11. DebateRound rejects empty round_id
# ---------------------------------------------------------------------------
expect_raises(
    "11. DebateRound rejects empty round_id",
    Exception,
    lambda: DebateRound(round_id="", horizon="short_term"),
)

# ---------------------------------------------------------------------------
# 12. DebateReport accepts valid report
# ---------------------------------------------------------------------------
try:
    report = DebateReport(debate_id="d-1", as_of="2026-01-01")
    assert report.debate_id == "d-1"
    assert report.schema_version == "1.0"
    ok("12. DebateReport accepts valid report")
except Exception as e:
    fail("12. DebateReport accepts valid report", e)

# ---------------------------------------------------------------------------
# 13. DebateReport rejects empty debate_id
# ---------------------------------------------------------------------------
expect_raises(
    "13. DebateReport rejects empty debate_id",
    Exception,
    lambda: DebateReport(debate_id="", as_of="2026-01-01"),
)

# ---------------------------------------------------------------------------
# 14. DebateReport rejects empty as_of
# ---------------------------------------------------------------------------
expect_raises(
    "14. DebateReport rejects empty as_of",
    Exception,
    lambda: DebateReport(debate_id="d-1", as_of=""),
)

# ---------------------------------------------------------------------------
# 15. DebateInputBundle accepts minimal bundle
# ---------------------------------------------------------------------------
try:
    bundle = DebateInputBundle(bundle_id="b-1", as_of="2026-01-01")
    assert bundle.bundle_id == "b-1"
    assert bundle.tool_results == []
    ok("15. DebateInputBundle accepts minimal bundle")
except Exception as e:
    fail("15. DebateInputBundle accepts minimal bundle", e)

# ---------------------------------------------------------------------------
# 16. DebateInputBundle rejects empty bundle_id
# ---------------------------------------------------------------------------
expect_raises(
    "16. DebateInputBundle rejects empty bundle_id",
    Exception,
    lambda: DebateInputBundle(bundle_id="", as_of="2026-01-01"),
)

# ---------------------------------------------------------------------------
# 17. DebateInputBundle rejects empty as_of
# ---------------------------------------------------------------------------
expect_raises(
    "17. DebateInputBundle rejects empty as_of",
    Exception,
    lambda: DebateInputBundle(bundle_id="b-1", as_of=""),
)

# ---------------------------------------------------------------------------
# 18. make_debate_issue_id deterministic
# ---------------------------------------------------------------------------
try:
    id1 = make_debate_issue_id("stale_evidence", "Data is stale", horizon="short_term", role="risk")
    id2 = make_debate_issue_id("stale_evidence", "Data is stale", horizon="short_term", role="risk")
    assert id1 == id2, f"IDs differ: {id1!r} vs {id2!r}"
    assert id1.startswith("debate_issue:")
    ok("18. make_debate_issue_id deterministic")
except Exception as e:
    fail("18. make_debate_issue_id deterministic", e)

# ---------------------------------------------------------------------------
# 19. make_debate_issue_id changes when inputs change
# ---------------------------------------------------------------------------
try:
    id_a = make_debate_issue_id("stale_evidence", "Data is stale")
    id_b = make_debate_issue_id("missing_evidence", "Data is stale")
    id_c = make_debate_issue_id("stale_evidence", "Data is very stale")
    assert id_a != id_b
    assert id_a != id_c
    assert id_b != id_c
    ok("19. make_debate_issue_id changes when inputs change")
except Exception as e:
    fail("19. make_debate_issue_id changes when inputs change", e)

# ---------------------------------------------------------------------------
# 20. make_debate_id deterministic
# ---------------------------------------------------------------------------
try:
    id1 = make_debate_id("bundle-1", "2026-01-01", ticker="AAPL")
    id2 = make_debate_id("bundle-1", "2026-01-01", ticker="AAPL")
    id3 = make_debate_id("bundle-2", "2026-01-01", ticker="AAPL")
    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("debate:")
    ok("20. make_debate_id deterministic")
except Exception as e:
    fail("20. make_debate_id deterministic", e)

# ---------------------------------------------------------------------------
# 21. extract_debate_evidence_ids collects ToolResult evidence IDs
# ---------------------------------------------------------------------------
try:
    tr1 = _make_tool_result(run_id="run-1", evidence_id="eid-tool-1")
    tr2 = _make_tool_result(run_id="run-1", evidence_id="eid-tool-2")
    bundle = _make_bundle(tool_results=[tr1, tr2])
    eids = extract_debate_evidence_ids(bundle)
    assert "eid-tool-1" in eids
    assert "eid-tool-2" in eids
    ok("21. extract_debate_evidence_ids collects ToolResult evidence IDs")
except Exception as e:
    fail("21. extract_debate_evidence_ids collects ToolResult evidence IDs", e)

# ---------------------------------------------------------------------------
# 22. extract_debate_evidence_ids collects AgentResult evidence refs
# ---------------------------------------------------------------------------
try:
    tr = _make_tool_result(run_id="run-1", evidence_id="eid-ar-1")
    ar = AgentResult(
        agent_name="test_agent",
        run_id="run-1",
        findings=[
            Finding(
                text="A finding",
                evidence=[EvidenceRef(evidence_id="eid-ar-1", excerpt="excerpt")],
            )
        ],
    )
    bundle = DebateInputBundle(
        bundle_id="b-1",
        as_of="2026-01-01",
        agent_result=ar,
        tool_results=[tr],
    )
    eids = extract_debate_evidence_ids(bundle)
    assert "eid-ar-1" in eids
    ok("22. extract_debate_evidence_ids collects AgentResult evidence refs")
except Exception as e:
    fail("22. extract_debate_evidence_ids collects AgentResult evidence refs", e)

# ---------------------------------------------------------------------------
# 23. issue_from_validation_item_for_debate preserves evidence_id/field_path
# ---------------------------------------------------------------------------
try:
    item = _make_validation_item(
        item_type="stale_data",
        evidence_id="eid-val-1",
        field_path="data.price",
        object_id="obj-val-1",
    )
    debate_issue = issue_from_validation_item_for_debate(item, horizon="short_term", role="risk")
    assert debate_issue.issue_type == "stale_evidence"
    assert debate_issue.evidence_id == "eid-val-1"
    assert debate_issue.field_path == "data.price"
    assert debate_issue.related_id == "obj-val-1"
    assert debate_issue.horizon == "short_term"
    assert debate_issue.role == "risk"
    ok("23. issue_from_validation_item_for_debate preserves evidence_id/field_path")
except Exception as e:
    fail("23. issue_from_validation_item_for_debate preserves evidence_id/field_path", e)

# ---------------------------------------------------------------------------
# 24. issue_from_staleness_finding_for_debate maps stale evidence
# ---------------------------------------------------------------------------
try:
    finding = _make_staleness_finding(
        status="stale",
        evidence_id="eid-stale-1",
        field_path="macro.cpi_timestamp",
        object_id="obj-stale-1",
    )
    debate_issue = issue_from_staleness_finding_for_debate(finding, horizon="medium_term", role="bear")
    assert debate_issue.issue_type == "stale_evidence"
    assert debate_issue.evidence_id == "eid-stale-1"
    assert debate_issue.field_path == "macro.cpi_timestamp"
    assert debate_issue.related_id == "obj-stale-1"
    ok("24. issue_from_staleness_finding_for_debate maps stale evidence")
except Exception as e:
    fail("24. issue_from_staleness_finding_for_debate maps stale evidence", e)

# ---------------------------------------------------------------------------
# 25. issue_from_critic_issue_for_debate maps missing_risk/conflict/overconfidence
# ---------------------------------------------------------------------------
try:
    ci_risk = _make_critic_issue(issue_type="missing_risk", evidence_id="eid-c-1")
    ci_conf = _make_critic_issue(issue_type="overconfidence", evidence_id="eid-c-2")
    ci_conf_iid = make_critic_issue_id("overconfidence", f"Critic issue of type overconfidence", "agent-1", "eid-c-2")
    ci_conf2 = CriticIssue(issue_id=ci_conf_iid, issue_type="overconfidence", message="Critic issue of type overconfidence", evidence_id="eid-c-2", target_id="agent-1")

    d_risk = issue_from_critic_issue_for_debate(ci_risk, horizon="long_term")
    d_conf = issue_from_critic_issue_for_debate(ci_conf2, horizon="short_term")

    assert d_risk.issue_type == "missing_risk"
    assert d_risk.evidence_id == "eid-c-1"
    assert d_conf.issue_type == "overconfidence"
    assert d_conf.evidence_id == "eid-c-2"
    ok("25. issue_from_critic_issue_for_debate maps missing_risk/conflict/overconfidence")
except Exception as e:
    fail("25. issue_from_critic_issue_for_debate maps missing_risk/conflict/overconfidence", e)

# ---------------------------------------------------------------------------
# 26. build_bull_position handles insufficient evidence safely
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    pos = build_bull_position("short_term", bundle, evidence_ids=[])
    assert pos.role == "bull"
    assert pos.horizon == "short_term"
    assert len(pos.claims) == 1
    assert pos.claims[0].claim_type == "evidence_gap"
    assert pos.claims[0].confidence == "insufficient_evidence"
    assert "investment advice" in pos.claims[0].text.lower()
    assert pos.evidence_ids == []
    ok("26. build_bull_position handles insufficient evidence safely")
except Exception as e:
    fail("26. build_bull_position handles insufficient evidence safely", e)

# ---------------------------------------------------------------------------
# 27. build_bear_position uses critic/staleness issues
# ---------------------------------------------------------------------------
try:
    ci = _make_critic_issue(issue_type="missing_risk", evidence_id="eid-bear-1")
    cr = CriticResult(
        critic_id="cr-1",
        as_of="2026-01-01",
        issues=[ci],
    )
    bundle = _make_bundle(critic_result=cr)
    eids = ["eid-bear-1"]
    debate_issues = [issue_from_critic_issue_for_debate(ci)]
    pos = build_bear_position("short_term", bundle, evidence_ids=eids, issues=debate_issues)
    assert pos.role == "bear"
    assert len(pos.claims) >= 1
    assert any("Not investment advice" in c.text for c in pos.claims)
    ok("27. build_bear_position uses critic/staleness issues")
except Exception as e:
    fail("27. build_bear_position uses critic/staleness issues", e)

# ---------------------------------------------------------------------------
# 28. build_risk_position highlights stale/missing risk issues
# ---------------------------------------------------------------------------
try:
    stale_issue = DebateIssue(
        issue_id="di-stale-1",
        issue_type="stale_evidence",
        message="CPI data is 90 days old",
    )
    overconf_issue = DebateIssue(
        issue_id="di-overconf-1",
        issue_type="overconfidence",
        message="Confidence score too high for available evidence",
    )
    bundle = _make_bundle()
    pos = build_risk_position(
        "long_term", bundle,
        evidence_ids=["eid-r-1"],
        issues=[stale_issue, overconf_issue],
    )
    assert pos.role == "risk"
    assert len(pos.claims) >= 1
    # Should have stale and overconfidence claims
    claim_texts = " ".join(c.text for c in pos.claims)
    assert "stale" in claim_texts.lower() or "overconfidence" in claim_texts.lower()
    assert "Not investment advice" in claim_texts
    ok("28. build_risk_position highlights stale/missing risk issues")
except Exception as e:
    fail("28. build_risk_position highlights stale/missing risk issues", e)

# ---------------------------------------------------------------------------
# 29. build_debate_round creates bull/bear/risk positions
# ---------------------------------------------------------------------------
try:
    tr = _make_tool_result(run_id="run-1", evidence_id="eid-rnd-1")
    bundle = _make_bundle(tool_results=[tr])
    rnd = build_debate_round("short_term", bundle)
    assert rnd.horizon == "short_term"
    assert rnd.bull_position is not None
    assert rnd.bear_position is not None
    assert rnd.risk_position is not None
    ok("29. build_debate_round creates bull/bear/risk positions")
except Exception as e:
    fail("29. build_debate_round creates bull/bear/risk positions", e)

# ---------------------------------------------------------------------------
# 30. build_debate_round returns insufficient_evidence when no evidence
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle(tool_results=[])
    rnd = build_debate_round("medium_term", bundle)
    assert rnd.status == "insufficient_evidence", f"Expected insufficient_evidence, got {rnd.status!r}"
    assert rnd.verdict == "insufficient_evidence", f"Expected insufficient_evidence verdict, got {rnd.verdict!r}"
    ok("30. build_debate_round returns insufficient_evidence when no evidence")
except Exception as e:
    fail("30. build_debate_round returns insufficient_evidence when no evidence", e)

# ---------------------------------------------------------------------------
# 31. run_debate_by_horizon returns exactly three rounds
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    assert len(report.rounds) == 3, f"Expected 3 rounds, got {len(report.rounds)}"
    ok("31. run_debate_by_horizon returns exactly three rounds")
except Exception as e:
    fail("31. run_debate_by_horizon returns exactly three rounds", e)

# ---------------------------------------------------------------------------
# 32. run_debate_by_horizon orders rounds short/medium/long
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    horizons = [r.horizon for r in report.rounds]
    assert horizons == ["short_term", "medium_term", "long_term"], f"Wrong order: {horizons}"
    ok("32. run_debate_by_horizon orders rounds short/medium/long")
except Exception as e:
    fail("32. run_debate_by_horizon orders rounds short/medium/long", e)

# ---------------------------------------------------------------------------
# 33. run_debate_by_horizon does not mutate input bundle
# ---------------------------------------------------------------------------
try:
    tr = _make_tool_result(run_id="run-1", evidence_id="eid-immut-1")
    bundle = _make_bundle(tool_results=[tr])
    original_len = len(bundle.tool_results)
    original_bundle_id = bundle.bundle_id
    report = run_debate_by_horizon(bundle)
    assert bundle.bundle_id == original_bundle_id
    assert len(bundle.tool_results) == original_len
    ok("33. run_debate_by_horizon does not mutate input bundle")
except Exception as e:
    fail("33. run_debate_by_horizon does not mutate input bundle", e)

# ---------------------------------------------------------------------------
# 34. debate_report_tool_result_from_report returns valid ToolResult
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    tr = debate_report_tool_result_from_report(run_id="run-1", report=report)
    assert isinstance(tr, ToolResult)
    assert tr.run_id == "run-1"
    assert len(tr.evidence_id) > 0
    ok("34. debate_report_tool_result_from_report returns valid ToolResult")
except Exception as e:
    fail("34. debate_report_tool_result_from_report returns valid ToolResult", e)

# ---------------------------------------------------------------------------
# 35. Debate ToolResult has stable tool_name and target
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle(ticker="TSLA")
    report = run_debate_by_horizon(bundle)
    tr = debate_report_tool_result_from_report(run_id="run-1", report=report)
    assert tr.tool_name == "debate_report"
    assert tr.ticker == "TSLA"
    assert "TSLA" in tr.inputs.get("target", "")
    ok("35. Debate ToolResult has stable tool_name and target")
except Exception as e:
    fail("35. Debate ToolResult has stable tool_name and target", e)

# ---------------------------------------------------------------------------
# 36. Debate ToolResult payload includes report, summary, calculation_version
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    tr = debate_report_tool_result_from_report(run_id="run-1", report=report)
    assert "report" in tr.outputs
    assert "summary" in tr.outputs
    assert "calculation_version" in tr.outputs
    assert tr.outputs["calculation_version"] == "debate_by_horizon_skeleton_v1"
    ok("36. Debate ToolResult payload includes report, summary, calculation_version")
except Exception as e:
    fail("36. Debate ToolResult payload includes report, summary, calculation_version", e)

# ---------------------------------------------------------------------------
# 37. Debate ToolResult evidence_id deterministic for identical report payload
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    tr1 = debate_report_tool_result_from_report(run_id="run-1", report=report)
    tr2 = debate_report_tool_result_from_report(run_id="run-1", report=report)
    assert tr1.evidence_id == tr2.evidence_id
    ok("37. Debate ToolResult evidence_id deterministic for identical report payload")
except Exception as e:
    fail("37. Debate ToolResult evidence_id deterministic for identical report payload", e)

# ---------------------------------------------------------------------------
# 38. Debate ToolResult evidence_id changes when report payload changes
# ---------------------------------------------------------------------------
try:
    bundle_a = _make_bundle(bundle_id="bundle-a")
    bundle_b = _make_bundle(bundle_id="bundle-b")
    report_a = run_debate_by_horizon(bundle_a)
    report_b = run_debate_by_horizon(bundle_b)
    tr_a = debate_report_tool_result_from_report(run_id="run-1", report=report_a)
    tr_b = debate_report_tool_result_from_report(run_id="run-1", report=report_b)
    assert tr_a.evidence_id != tr_b.evidence_id, "evidence_ids should differ for different reports"
    ok("38. Debate ToolResult evidence_id changes when report payload changes")
except Exception as e:
    fail("38. Debate ToolResult evidence_id changes when report payload changes", e)

# ---------------------------------------------------------------------------
# 39. summarize_debate_report returns expected summary
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    summary = summarize_debate_report(report)
    assert "debate_id" in summary
    assert "ticker" in summary
    assert "status" in summary
    assert "recommendation" in summary
    assert "round_count" in summary
    assert summary["round_count"] == 3
    assert "issue_count" in summary
    assert "critical_count" in summary
    assert "warning_count" in summary
    assert "info_count" in summary
    assert "horizon_verdicts" in summary
    assert "horizon_statuses" in summary
    assert "top_messages" in summary
    assert isinstance(summary["top_messages"], list)
    assert len(summary["top_messages"]) <= 10
    ok("39. summarize_debate_report returns expected summary")
except Exception as e:
    fail("39. summarize_debate_report returns expected summary", e)

# ---------------------------------------------------------------------------
# 40. DebateReport serialization roundtrip
# ---------------------------------------------------------------------------
try:
    bundle = _make_bundle()
    report = run_debate_by_horizon(bundle)
    dumped = report.model_dump(mode="json")
    restored = DebateReport.model_validate(dumped)
    assert restored.debate_id == report.debate_id
    assert restored.as_of == report.as_of
    assert restored.status == report.status
    assert restored.recommendation == report.recommendation
    assert len(restored.rounds) == len(report.rounds)
    ok("40. DebateReport serialization roundtrip")
except Exception as e:
    fail("40. DebateReport serialization roundtrip", e)

# ---------------------------------------------------------------------------
# 41. DebateIssue serialization roundtrip
# ---------------------------------------------------------------------------
try:
    issue = DebateIssue(
        issue_id="di-rt-1",
        issue_type="stale_evidence",
        message="Test stale evidence",
        horizon="short_term",
        role="risk",
        evidence_id="eid-rt-1",
    )
    dumped = issue.model_dump(mode="json")
    restored = DebateIssue.model_validate(dumped)
    assert restored.issue_id == issue.issue_id
    assert restored.issue_type == issue.issue_type
    assert restored.evidence_id == issue.evidence_id
    ok("41. DebateIssue serialization roundtrip")
except Exception as e:
    fail("41. DebateIssue serialization roundtrip", e)

# ---------------------------------------------------------------------------
# 42. No live app modules are imported
# ---------------------------------------------------------------------------
try:
    import sys
    forbidden = ["app", "pages", "lib.llm_orchestrator", "lib.workflow_state"]
    loaded = set(sys.modules.keys())
    for mod in forbidden:
        matches = [m for m in loaded if m == mod or m.startswith(mod + ".")]
        if matches:
            raise ImportError(f"Forbidden module loaded: {matches}")
    ok("42. No live app modules are imported")
except Exception as e:
    fail("42. No live app modules are imported", e)

# ---------------------------------------------------------------------------
# 43. No external API/network calls are made (structural check)
# ---------------------------------------------------------------------------
try:
    import lib.reliability.debate as debate_mod
    src = open(debate_mod.__file__).read()
    forbidden_patterns = ["requests.get", "requests.post", "urllib.request", "httpx", "aiohttp"]
    for pat in forbidden_patterns:
        assert pat not in src, f"Forbidden network pattern found: {pat!r}"
    ok("43. No external API/network calls are made")
except Exception as e:
    fail("43. No external API/network calls are made", e)

# ---------------------------------------------------------------------------
# 44. No Claude/LLM API is called
# ---------------------------------------------------------------------------
try:
    import lib.reliability.debate as debate_mod
    src = open(debate_mod.__file__).read()
    llm_patterns = ["anthropic", "openai", "claude", "ChatCompletion", "messages.create"]
    for pat in llm_patterns:
        assert pat not in src, f"Forbidden LLM pattern found: {pat!r}"
    ok("44. No Claude/LLM API is called")
except Exception as e:
    fail("44. No Claude/LLM API is called", e)

# ---------------------------------------------------------------------------
# 45. Existing debate-adjacent imports are accessible (regression guard)
# ---------------------------------------------------------------------------
try:
    import lib.reliability.macro_agent as _ma
    import lib.reliability.horizon_synthesis as _hs
    import lib.reliability.orchestration as _orch
    assert hasattr(_ma, "run_macro_agent_v0")
    assert hasattr(_hs, "run_horizon_aware_synthesis")
    assert hasattr(_orch, "build_orchestration_report")
    ok("45. Existing macro agent / horizon synthesis / orchestration modules importable")
except Exception as e:
    fail("45. Existing macro agent / horizon synthesis / orchestration modules importable", e)


# ===========================================================================
# Phase 3B Integration Regression Tests (tests 46–54)
# Verify debate.py correctly consumes the accepted Phase 3B field names:
#   card.horizon  (not card.bucket)
#   evidence_summary.supporting_evidence_ids  (not evidence_ids)
# ===========================================================================

def _make_phase3b_hsr() -> HorizonSynthesisReport:
    """Real Phase 3B HorizonSynthesisReport with three cards."""
    esummary_short = HorizonEvidenceSummary(
        horizon="short_term",
        evidence_count=1,
        supporting_evidence_ids=["ev_short"],
    )
    esummary_medium = HorizonEvidenceSummary(
        horizon="medium_term",
        evidence_count=1,
        supporting_evidence_ids=["ev_medium"],
    )
    esummary_long = HorizonEvidenceSummary(
        horizon="long_term",
        evidence_count=1,
        supporting_evidence_ids=["ev_long"],
    )
    card_short = HorizonSynthesisCard(
        horizon="short_term",
        signal_direction="bullish",
        evidence_summary=esummary_short,
    )
    card_medium = HorizonSynthesisCard(
        horizon="medium_term",
        signal_direction="mixed",
        evidence_summary=esummary_medium,
    )
    card_long = HorizonSynthesisCard(
        horizon="long_term",
        signal_direction="bearish",
        evidence_summary=esummary_long,
    )
    return HorizonSynthesisReport(
        synthesis_id="test-hsr-phase3b",
        as_of="2026-01-01",
        ticker="TEST",
        cards=[card_short, card_medium, card_long],
    )


# ---------------------------------------------------------------------------
# 46. extract_debate_evidence_ids returns short_term card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    eids = extract_debate_evidence_ids(bundle, horizon="short_term")
    assert "ev_short" in eids, f"Expected 'ev_short' in {eids}"
    assert "ev_medium" not in eids or eids.index("ev_short") < eids.index("ev_medium"), \
        "ev_short should appear before other horizon IDs"
    ok("46. extract_debate_evidence_ids returns short_term supporting_evidence_ids")
except Exception as e:
    fail("46. extract_debate_evidence_ids returns short_term supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 47. extract_debate_evidence_ids returns medium_term card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    eids = extract_debate_evidence_ids(bundle, horizon="medium_term")
    assert "ev_medium" in eids, f"Expected 'ev_medium' in {eids}"
    ok("47. extract_debate_evidence_ids returns medium_term supporting_evidence_ids")
except Exception as e:
    fail("47. extract_debate_evidence_ids returns medium_term supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 48. extract_debate_evidence_ids returns long_term card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    eids = extract_debate_evidence_ids(bundle, horizon="long_term")
    assert "ev_long" in eids, f"Expected 'ev_long' in {eids}"
    ok("48. extract_debate_evidence_ids returns long_term supporting_evidence_ids")
except Exception as e:
    fail("48. extract_debate_evidence_ids returns long_term supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 49. _get_horizon_synthesis_card finds card by card.horizon (Phase 3B field)
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    card_s = _get_horizon_synthesis_card("short_term", bundle)
    card_m = _get_horizon_synthesis_card("medium_term", bundle)
    card_l = _get_horizon_synthesis_card("long_term", bundle)
    assert card_s is not None, "short_term card not found"
    assert card_m is not None, "medium_term card not found"
    assert card_l is not None, "long_term card not found"
    assert card_s.horizon == "short_term"
    assert card_m.horizon == "medium_term"
    assert card_l.horizon == "long_term"
    ok("49. _get_horizon_synthesis_card finds card by card.horizon")
except Exception as e:
    fail("49. _get_horizon_synthesis_card finds card by card.horizon", e)

# ---------------------------------------------------------------------------
# 50. run_debate_by_horizon with real Phase 3B HSR creates exactly 3 rounds
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    report = run_debate_by_horizon(bundle)
    assert len(report.rounds) == 3, f"Expected 3 rounds, got {len(report.rounds)}"
    horizons = [r.horizon for r in report.rounds]
    assert horizons == ["short_term", "medium_term", "long_term"], f"Wrong order: {horizons}"
    ok("50. run_debate_by_horizon with real Phase 3B HSR creates exactly 3 rounds")
except Exception as e:
    fail("50. run_debate_by_horizon with real Phase 3B HSR creates exactly 3 rounds", e)

# ---------------------------------------------------------------------------
# 51. Short-term round uses ev_short from Phase 3B card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    report = run_debate_by_horizon(bundle)
    short_round = next(r for r in report.rounds if r.horizon == "short_term")
    bull = short_round.bull_position
    assert bull is not None, "short_term bull position is None"
    assert "ev_short" in bull.evidence_ids, \
        f"ev_short not in short_term bull evidence_ids: {bull.evidence_ids}"
    ok("51. Short-term round uses ev_short from Phase 3B supporting_evidence_ids")
except Exception as e:
    fail("51. Short-term round uses ev_short from Phase 3B supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 52. Medium-term round uses ev_medium from Phase 3B card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    report = run_debate_by_horizon(bundle)
    medium_round = next(r for r in report.rounds if r.horizon == "medium_term")
    bull = medium_round.bull_position
    assert bull is not None, "medium_term bull position is None"
    assert "ev_medium" in bull.evidence_ids, \
        f"ev_medium not in medium_term bull evidence_ids: {bull.evidence_ids}"
    ok("52. Medium-term round uses ev_medium from Phase 3B supporting_evidence_ids")
except Exception as e:
    fail("52. Medium-term round uses ev_medium from Phase 3B supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 53. Long-term round uses ev_long from Phase 3B card supporting_evidence_ids
# ---------------------------------------------------------------------------
try:
    hsr = _make_phase3b_hsr()
    bundle = DebateInputBundle(
        bundle_id="b-phase3b",
        as_of="2026-01-01",
        horizon_synthesis_report=hsr,
    )
    report = run_debate_by_horizon(bundle)
    long_round = next(r for r in report.rounds if r.horizon == "long_term")
    bull = long_round.bull_position
    assert bull is not None, "long_term bull position is None"
    assert "ev_long" in bull.evidence_ids, \
        f"ev_long not in long_term bull evidence_ids: {bull.evidence_ids}"
    ok("53. Long-term round uses ev_long from Phase 3B supporting_evidence_ids")
except Exception as e:
    fail("53. Long-term round uses ev_long from Phase 3B supporting_evidence_ids", e)

# ---------------------------------------------------------------------------
# 54. Backward-compatible bucket fallback (secondary; Phase 3B field preferred)
# ---------------------------------------------------------------------------
try:
    from types import SimpleNamespace

    # Simulate a legacy duck-typed card that only has bucket and evidence_ids
    legacy_esummary = SimpleNamespace(evidence_ids=["ev_legacy"], supporting_evidence_ids=None)
    legacy_card = SimpleNamespace(bucket="short_term", horizon=None, signal_direction="mixed",
                                  evidence_summary=legacy_esummary)
    legacy_hsr = SimpleNamespace(cards=[legacy_card], synthesis_id="legacy-hsr")
    bundle = DebateInputBundle(
        bundle_id="b-legacy",
        as_of="2026-01-01",
        horizon_synthesis_report=legacy_hsr,
    )
    eids = extract_debate_evidence_ids(bundle, horizon="short_term")
    assert "ev_legacy" in eids, f"Backward-compat fallback failed; got {eids}"
    ok("54. Backward-compatible bucket/evidence_ids fallback still works")
except Exception as e:
    fail("54. Backward-compatible bucket/evidence_ids fallback still works", e)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
print()
print(f"Results: {_PASS} passed, {_FAIL} failed out of {_PASS + _FAIL} tests")
if _FAIL > 0:
    sys.exit(1)
else:
    print("All debate skeleton tests passed.")
    sys.exit(0)
