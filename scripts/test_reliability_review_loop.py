"""
scripts/test_reliability_review_loop.py

Phase 3G: Offline Review Loop / Reliability Run Report Skeleton — test suite.

Tests cover:
  - ReliabilityRunInputBundle construction and validation.
  - ReliabilityRunSummary construction and enforcement.
  - ReliabilityRunReport construction, model_validator enforcement.
  - make_reliability_run_report_id: deterministic, stable output.
  - determine_reliability_run_status:
      critical human review → blocked,
      changes_requested → needs_revision,
      approved_for_research_only → complete,
      missing human_review_report → unknown.
  - collect_reliability_run_source_ids: collection, deduplication, order.
  - summarize_reliability_run: counts, reasons, approved_for_execution=False.
  - build_reliability_run_report: complete roundtrip from mock artifacts.
  - Deterministic: identical inputs → identical report_ids.
  - Missing optional artifacts → warnings without crashing.
  - Inputs are not mutated.
  - reliability_run_tool_result_from_report: tool_name, payload, evidence_id.
  - approved_for_execution is always False throughout.
  - __all__ exports include Phase 3G public symbols.
  - No dependency on Streamlit, live LLM, broker/order modules, or network.
  - Regression: run prior Phase 3 test scripts.

Usage:
    python3 scripts/test_reliability_review_loop.py
"""

import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import copy
import json
import subprocess
from typing import Any, Optional

import pydantic

from lib.reliability.review_loop import (
    ReliabilityRunInputBundle,
    ReliabilityRunReport,
    ReliabilityRunStatus,
    ReliabilityRunSummary,
    _CALCULATION_VERSION,
    _REVIEW_LOOP_TOOL_NAME,
    build_reliability_run_report,
    collect_reliability_run_source_ids,
    determine_reliability_run_status,
    make_reliability_run_report_id,
    reliability_run_tool_result_from_report,
    summarize_reliability_run,
)
from lib.reliability.human_review import (
    HumanReviewInputBundle,
    HumanReviewReport,
    run_human_review_skeleton,
    make_human_review_report_id,
    HumanFeedbackItem,
    make_human_feedback_id,
    HumanReviewOutcome,
    HumanRevisionRequest,
    build_human_review_report,
    determine_human_review_outcome,
)
from lib.reliability.decision_packet import (
    DecisionPacket,
    DecisionPacketInputBundle,
    run_decision_packet_synthesis,
)
from lib.reliability.debate import (
    DebateInputBundle,
    run_debate_by_horizon,
)
from lib.reliability.horizon_synthesis import (
    HorizonSynthesisInputBundle,
    run_horizon_aware_synthesis,
)
from lib.reliability.critic import CriticResult, run_mock_critic
from lib.reliability.staleness import StalenessReport, aggregate_staleness_findings
from lib.reliability.validation_aggregator import (
    ValidationAggregate,
    aggregate_validation_items,
    warning_to_validation_item,
)
from lib.reliability.schemas import ToolResult
from lib.reliability.adapters import stable_hash_payload


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_failed_tests: list[str] = []


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def fail(label: str, reason: str) -> None:
    global FAIL
    FAIL += 1
    _failed_tests.append(f"{label}: {reason}")
    print(f"  FAIL  {label} — {reason}")


def check(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        ok(label)
    else:
        fail(label, reason or "condition is False")


def _utcnow_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Mock artifact builders
# ---------------------------------------------------------------------------

def _make_tool_result(run_id: str, ticker: str, n: int = 0) -> ToolResult:
    from lib.reliability.adapters import make_evidence_id
    payload = {"ticker": ticker, "n": n, "run_id": run_id}
    eid = make_evidence_id(
        run_id=run_id,
        tool_name="mock_tool",
        target=ticker,
        metric_group="mock",
        payload=payload,
    )
    return ToolResult(
        evidence_id=eid,
        tool_name="mock_tool",
        run_id=run_id,
        ticker=ticker,
        inputs={"ticker": ticker},
        outputs=payload,
        description=f"Mock tool result {n} for {ticker}.",
    )


def _make_validation_aggregate(ticker: str, run_id: str) -> ValidationAggregate:
    from datetime import datetime, timezone
    items = [
        warning_to_validation_item(
            f"Warning {i} for {ticker}",
            domain="agent_result",
            object_id=run_id,
            item_type="unsupported",
            severity="warning",
        )
        for i in range(2)
    ]
    return aggregate_validation_items(
        aggregate_id=f"agg_{run_id}",
        as_of=datetime.now(timezone.utc).isoformat(),
        items=items,
    )


def _make_staleness_report(ticker: str, run_id: str) -> StalenessReport:
    from datetime import datetime, timezone
    return aggregate_staleness_findings(
        report_id=f"sr_{run_id}",
        as_of=datetime.now(timezone.utc).isoformat(),
        findings=[],
        target=ticker,
    )


def _make_critic_result(
    ticker: str, run_id: str, va: ValidationAggregate, sr: StalenessReport
) -> CriticResult:
    from datetime import datetime, timezone
    return run_mock_critic(
        critic_id=f"cr_{run_id}",
        as_of=datetime.now(timezone.utc).isoformat(),
        agent_result=None,
        validation_aggregate=va,
        staleness_report=sr,
    )


def _make_debate_report(ticker: str, run_id: str, trs: list[ToolResult]):
    bundle = DebateInputBundle(
        bundle_id=f"debate_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
        tool_results=trs,
    )
    return run_debate_by_horizon(bundle)


def _make_horizon_synthesis_report(ticker: str, run_id: str, trs: list[ToolResult]):
    from lib.reliability.validation_aggregator import aggregate_validation_items
    bundle = HorizonSynthesisInputBundle(
        bundle_id=f"hsyn_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
        tool_results=trs,
    )
    return run_horizon_aware_synthesis(bundle)


def _make_decision_packet(
    ticker: str,
    run_id: str,
    trs: list[ToolResult],
    debate_report: Any,
    hsr: Any,
    va: ValidationAggregate,
    sr: StalenessReport,
    cr: CriticResult,
):
    bundle = DecisionPacketInputBundle(
        bundle_id=f"dp_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
        debate_report=debate_report,
        horizon_synthesis_report=hsr,
        validation_aggregate=va,
        staleness_report=sr,
        critic_result=cr,
        tool_results=trs,
    )
    return run_decision_packet_synthesis(bundle)


def _make_human_review_report_clean(ticker: str, run_id: str) -> HumanReviewReport:
    """Create a clean human review report (no critical feedback)."""
    bundle = HumanReviewInputBundle(
        bundle_id=f"hr_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
    )
    return run_human_review_skeleton(bundle)


def _make_human_review_report_blocked(ticker: str, run_id: str) -> HumanReviewReport:
    """Create a human review report with critical feedback → blocked."""
    crit_fb = HumanFeedbackItem(
        feedback_id=make_human_feedback_id("safety_concern", "Critical safety issue", "manual"),
        feedback_type="safety_concern",
        severity="critical",
        message="Critical safety issue requiring block.",
        source_type="manual",
    )
    outcome = determine_human_review_outcome(
        feedback_items=[crit_fb],
        revision_requests=[],
    )
    report_id = make_human_review_report_id(
        bundle_id=f"hr_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
    )
    return build_human_review_report(
        review_report_id=report_id,
        as_of=_utcnow_str(),
        ticker=ticker,
        feedback_items=[crit_fb],
        outcome=outcome,
    )


def _make_human_review_report_revision(ticker: str, run_id: str) -> HumanReviewReport:
    """Create a human review report with warning feedback → changes_requested."""
    warn_fb = HumanFeedbackItem(
        feedback_id=make_human_feedback_id("evidence_gap", "Evidence gap found", "manual"),
        feedback_type="evidence_gap",
        severity="warning",
        message="Evidence gap found; additional evidence required.",
        source_type="manual",
    )
    outcome = determine_human_review_outcome(
        feedback_items=[warn_fb],
        revision_requests=[],
    )
    report_id = make_human_review_report_id(
        bundle_id=f"hr_bundle_{run_id}",
        as_of=_utcnow_str(),
        ticker=ticker,
    )
    return build_human_review_report(
        review_report_id=report_id,
        as_of=_utcnow_str(),
        ticker=ticker,
        feedback_items=[warn_fb],
        outcome=outcome,
    )


def _make_full_input_bundle(
    ticker: str,
    run_id: str,
    human_review_report: Optional[HumanReviewReport] = None,
    include_all: bool = True,
) -> ReliabilityRunInputBundle:
    trs = [_make_tool_result(run_id, ticker, i) for i in range(3)]
    va = _make_validation_aggregate(ticker, run_id)
    sr = _make_staleness_report(ticker, run_id)
    cr = _make_critic_result(ticker, run_id, va, sr)
    dr = _make_debate_report(ticker, run_id, trs) if include_all else None
    hsr = _make_horizon_synthesis_report(ticker, run_id, trs) if include_all else None
    dp = _make_decision_packet(ticker, run_id, trs, dr, hsr, va, sr, cr) if include_all else None
    hrr = human_review_report if human_review_report is not None else (
        _make_human_review_report_clean(ticker, run_id) if include_all else None
    )
    return ReliabilityRunInputBundle(
        bundle_id=f"bundle_{run_id}",
        run_id=run_id,
        as_of=_utcnow_str(),
        ticker=ticker,
        orchestration_report=None,  # Phase 3A not fully wired in full_bundle for simplicity
        horizon_synthesis_report=hsr,
        macro_agent_result=None,
        debate_report=dr,
        decision_packet=dp,
        human_review_report=hrr,
        validation_aggregate=va,
        staleness_report=sr,
        critic_result=cr,
        tool_results=trs,
    )


# ---------------------------------------------------------------------------
# Test group 1: ReliabilityRunInputBundle construction
# ---------------------------------------------------------------------------

print("\n[1] ReliabilityRunInputBundle construction")

bundle_min = ReliabilityRunInputBundle(
    bundle_id="b1",
    run_id="run_001",
    as_of="2026-05-23T00:00:00+00:00",
)
check("1a. Minimal bundle constructs OK", bundle_min.bundle_id == "b1")
check("1b. Minimal bundle run_id", bundle_min.run_id == "run_001")
check("1c. Minimal bundle has no ticker", bundle_min.ticker is None)
check("1d. All optional artifacts are None", all([
    bundle_min.orchestration_report is None,
    bundle_min.horizon_synthesis_report is None,
    bundle_min.macro_agent_result is None,
    bundle_min.debate_report is None,
    bundle_min.decision_packet is None,
    bundle_min.human_review_report is None,
    bundle_min.validation_aggregate is None,
    bundle_min.staleness_report is None,
    bundle_min.critic_result is None,
]))
check("1e. tool_results defaults to empty list", bundle_min.tool_results == [])

try:
    ReliabilityRunInputBundle(bundle_id="b1", run_id="   ", as_of="2026-01-01")
    fail("1f. Whitespace run_id should raise", "did not raise")
except pydantic.ValidationError:
    ok("1f. Whitespace run_id raises ValidationError")

try:
    ReliabilityRunInputBundle(bundle_id="b1", run_id="run1", as_of="   ")
    fail("1g. Whitespace as_of should raise", "did not raise")
except pydantic.ValidationError:
    ok("1g. Whitespace as_of raises ValidationError")

try:
    ReliabilityRunInputBundle(bundle_id="b1", run_id="r", as_of="t", unknown_field="x")
    fail("1h. Extra field should raise", "did not raise")
except pydantic.ValidationError:
    ok("1h. Extra field raises ValidationError")


# ---------------------------------------------------------------------------
# Test group 2: ReliabilityRunSummary enforcement
# ---------------------------------------------------------------------------

print("\n[2] ReliabilityRunSummary enforcement")

summ = ReliabilityRunSummary(target="AAPL", run_id="run_001", status="unknown")
check("2a. Summary constructs OK", summ.target == "AAPL")
check("2b. approved_for_execution is False", summ.approved_for_execution is False)
check("2c. Default counts are 0", summ.horizon_count == 0 and summ.evidence_count == 0)

try:
    ReliabilityRunSummary(target="AAPL", run_id="r", approved_for_execution=True)
    fail("2d. approved_for_execution=True should raise", "did not raise")
except pydantic.ValidationError:
    ok("2d. approved_for_execution=True raises ValidationError")


# ---------------------------------------------------------------------------
# Test group 3: ReliabilityRunReport enforcement
# ---------------------------------------------------------------------------

print("\n[3] ReliabilityRunReport enforcement")

_summ = ReliabilityRunSummary(target="AAPL", run_id="r001", status="unknown")
rpt = ReliabilityRunReport(
    report_id="rlr_abc123",
    target="AAPL",
    run_id="r001",
    as_of="2026-05-23T00:00:00",
    status="unknown",
    summary=_summ,
    created_at="2026-05-23T00:00:00",
)
check("3a. Report constructs OK", rpt.report_id == "rlr_abc123")
check("3b. Report approved_for_execution is False", rpt.approved_for_execution is False)
check("3c. Report calculation_version matches constant", rpt.calculation_version == _CALCULATION_VERSION)

try:
    ReliabilityRunReport(
        report_id="r1",
        target="X",
        run_id="r",
        as_of="t",
        status="unknown",
        summary=_summ,
        created_at="t",
        approved_for_execution=True,
    )
    fail("3d. approved_for_execution=True should raise", "did not raise")
except pydantic.ValidationError:
    ok("3d. approved_for_execution=True raises ValidationError")

try:
    ReliabilityRunReport(
        report_id="  ",
        target="X",
        run_id="r",
        as_of="t",
        status="unknown",
        summary=_summ,
        created_at="t",
    )
    fail("3e. Whitespace report_id should raise", "did not raise")
except pydantic.ValidationError:
    ok("3e. Whitespace report_id raises ValidationError")


# ---------------------------------------------------------------------------
# Test group 4: make_reliability_run_report_id
# ---------------------------------------------------------------------------

print("\n[4] make_reliability_run_report_id")

id1 = make_reliability_run_report_id("run_001", "AAPL", "2026-05-23")
id2 = make_reliability_run_report_id("run_001", "AAPL", "2026-05-23")
id3 = make_reliability_run_report_id("run_002", "AAPL", "2026-05-23")

check("4a. Same inputs → same ID", id1 == id2)
check("4b. Different run_id → different ID", id1 != id3)
check("4c. ID has rlr_ prefix", id1.startswith("rlr_"))
check("4d. ID is non-empty", len(id1) > 4)


# ---------------------------------------------------------------------------
# Test group 5: determine_reliability_run_status
# ---------------------------------------------------------------------------

print("\n[5] determine_reliability_run_status")

# 5a. No human_review_report → unknown
bundle_no_hrr = ReliabilityRunInputBundle(
    bundle_id="b_no_hrr", run_id="run_no_hrr", as_of="2026-05-23",
    ticker="AAPL",
)
status5a, br5a, rr5a = determine_reliability_run_status(bundle_no_hrr)
check("5a. No human review → unknown", status5a == "unknown")
check("5b. No human review → no blocking reasons", len(br5a) == 0)

# 5c. Blocked human review → blocked status
hrr_blocked = _make_human_review_report_blocked("MSFT", "run_blocked")
bundle_blocked = ReliabilityRunInputBundle(
    bundle_id="b_blocked", run_id="run_blocked", as_of="2026-05-23",
    ticker="MSFT",
    human_review_report=hrr_blocked,
)
status5c, br5c, rr5c = determine_reliability_run_status(bundle_blocked)
check("5c. Blocked human review → blocked", status5c == "blocked")
check("5d. Blocked → blocking_reasons populated", len(br5c) > 0)

# 5e. Revision-request human review → needs_revision
hrr_revision = _make_human_review_report_revision("GOOG", "run_revision")
bundle_revision = ReliabilityRunInputBundle(
    bundle_id="b_revision", run_id="run_revision", as_of="2026-05-23",
    ticker="GOOG",
    human_review_report=hrr_revision,
)
status5e, br5e, rr5e = determine_reliability_run_status(bundle_revision)
check("5e. Revision human review → needs_revision", status5e == "needs_revision")
check("5f. Revision → revision_reasons populated", len(rr5e) > 0)
check("5g. Revision → no blocking reasons", len(br5e) == 0)

# 5h. Clean human review → complete
hrr_clean = _make_human_review_report_clean("NVDA", "run_clean")
bundle_clean = ReliabilityRunInputBundle(
    bundle_id="b_clean", run_id="run_clean", as_of="2026-05-23",
    ticker="NVDA",
    human_review_report=hrr_clean,
)
status5h, br5h, rr5h = determine_reliability_run_status(bundle_clean)
check("5h. Clean human review → complete", status5h == "complete")
check("5i. Clean → no blocking reasons", len(br5h) == 0)
check("5j. Clean → no revision reasons", len(rr5h) == 0)

# 5k. Blocked takes priority over everything
check("5k. Blocked status dominates", status5c == "blocked")


# ---------------------------------------------------------------------------
# Test group 6: collect_reliability_run_source_ids
# ---------------------------------------------------------------------------

print("\n[6] collect_reliability_run_source_ids")

run_id_src = "run_src_test"
ticker_src = "TSLA"
trs_src = [_make_tool_result(run_id_src, ticker_src, i) for i in range(3)]
va_src = _make_validation_aggregate(ticker_src, run_id_src)
sr_src = _make_staleness_report(ticker_src, run_id_src)
cr_src = _make_critic_result(ticker_src, run_id_src, va_src, sr_src)

bundle_src = ReliabilityRunInputBundle(
    bundle_id="b_src",
    run_id=run_id_src,
    as_of="2026-05-23",
    ticker=ticker_src,
    validation_aggregate=va_src,
    staleness_report=sr_src,
    critic_result=cr_src,
    tool_results=trs_src,
)
source_ids = collect_reliability_run_source_ids(bundle_src)

check("6a. source_ids is a list", isinstance(source_ids, list))
check("6b. Contains tool result evidence IDs", all(
    tr.evidence_id in source_ids for tr in trs_src
))
check("6c. Contains validation aggregate ID", va_src.aggregate_id in source_ids)
check("6d. Contains staleness report ID", sr_src.report_id in source_ids)
check("6e. Contains critic result ID", cr_src.critic_id in source_ids)
check("6f. No duplicates", len(source_ids) == len(set(source_ids)))

# Deduplication test
bundle_dup = ReliabilityRunInputBundle(
    bundle_id="b_dup",
    run_id=run_id_src,
    as_of="2026-05-23",
    ticker=ticker_src,
    tool_results=trs_src,  # same tool results → same evidence IDs
    validation_aggregate=va_src,
)
source_ids_dup = collect_reliability_run_source_ids(bundle_dup)
check("6g. Deduplication preserves uniqueness", len(source_ids_dup) == len(set(source_ids_dup)))

# Determinism
source_ids_2 = collect_reliability_run_source_ids(bundle_src)
check("6h. Deterministic source ID collection", source_ids == source_ids_2)


# ---------------------------------------------------------------------------
# Test group 7: summarize_reliability_run
# ---------------------------------------------------------------------------

print("\n[7] summarize_reliability_run")

bundle_summ = _make_full_input_bundle("AMD", "run_summ", include_all=True)
src_ids_summ = collect_reliability_run_source_ids(bundle_summ)
status_summ, br_summ, rr_summ = determine_reliability_run_status(bundle_summ)
summary = summarize_reliability_run(
    bundle_summ, status_summ, src_ids_summ, br_summ, rr_summ
)

check("7a. Summary target matches ticker", summary.target == "AMD")
check("7b. Summary run_id matches", summary.run_id == "run_summ")
check("7c. Summary approved_for_execution is False", summary.approved_for_execution is False)
check("7d. Summary evidence_count > 0", summary.evidence_count > 0)
check("7e. Summary horizon_count >= 0", summary.horizon_count >= 0)
check("7f. Summary debate_count >= 0", summary.debate_count >= 0)
check("7g. Summary validation_issue_count >= 0", summary.validation_issue_count >= 0)
check("7h. Summary staleness_issue_count >= 0", summary.staleness_issue_count >= 0)
check("7i. Summary critic_issue_count >= 0", summary.critic_issue_count >= 0)
check("7j. Summary status is valid ReliabilityRunStatus", summary.status in (
    "unknown", "complete", "needs_revision", "blocked", "failed"
))

# With clean human review: summary review_status populated
hrr_for_summ = _make_human_review_report_clean("AMD", "run_summ")
bundle_summ_clean = ReliabilityRunInputBundle(
    bundle_id="b_summ_clean",
    run_id="run_summ_clean",
    as_of="2026-05-23",
    ticker="AMD",
    human_review_report=hrr_for_summ,
)
src_ids_sc = collect_reliability_run_source_ids(bundle_summ_clean)
status_sc, br_sc, rr_sc = determine_reliability_run_status(bundle_summ_clean)
summ_clean = summarize_reliability_run(bundle_summ_clean, status_sc, src_ids_sc, br_sc, rr_sc)
check("7k. Summary review_status populated when HRR present", summ_clean.review_status is not None)


# ---------------------------------------------------------------------------
# Test group 8: build_reliability_run_report — full roundtrip
# ---------------------------------------------------------------------------

print("\n[8] build_reliability_run_report — full roundtrip")

bundle_full = _make_full_input_bundle("NVDA", "run_full_3g", include_all=True)
report = build_reliability_run_report(bundle_full, created_at="2026-05-23T12:00:00")

check("8a. Report constructs OK", isinstance(report, ReliabilityRunReport))
check("8b. Report report_id has rlr_ prefix", report.report_id.startswith("rlr_"))
check("8c. Report target matches ticker", report.target == "NVDA")
check("8d. Report run_id matches", report.run_id == "run_full_3g")
check("8e. Report approved_for_execution is False", report.approved_for_execution is False)
check("8f. Report summary.approved_for_execution is False", report.summary.approved_for_execution is False)
check("8g. Report source_ids is list", isinstance(report.source_ids, list))
check("8h. Report source_ids has entries", len(report.source_ids) > 0)
check("8i. Report warnings is list", isinstance(report.warnings, list))
check("8j. Report calculation_version is correct", report.calculation_version == _CALCULATION_VERSION)
check("8k. Report status is valid", report.status in (
    "unknown", "complete", "needs_revision", "blocked", "failed"
))


# ---------------------------------------------------------------------------
# Test group 9: Determinism — identical inputs → identical report_ids
# ---------------------------------------------------------------------------

print("\n[9] Determinism")

bundle_det1 = ReliabilityRunInputBundle(
    bundle_id="det_b1",
    run_id="run_det",
    as_of="2026-05-23T00:00:00",
    ticker="AAPL",
)
bundle_det2 = ReliabilityRunInputBundle(
    bundle_id="det_b1",
    run_id="run_det",
    as_of="2026-05-23T00:00:00",
    ticker="AAPL",
)
# Use fixed created_at to ensure full determinism
report_det1 = build_reliability_run_report(bundle_det1, created_at="2026-05-23T00:00:00")
report_det2 = build_reliability_run_report(bundle_det2, created_at="2026-05-23T00:00:00")

check("9a. Identical inputs → identical report_id", report_det1.report_id == report_det2.report_id)
check("9b. Identical inputs → identical status", report_det1.status == report_det2.status)
check("9c. Identical inputs → identical source_ids", report_det1.source_ids == report_det2.source_ids)

# Different inputs → different report_ids
bundle_det3 = ReliabilityRunInputBundle(
    bundle_id="det_b2",
    run_id="run_det_2",
    as_of="2026-05-23T00:00:00",
    ticker="MSFT",
)
report_det3 = build_reliability_run_report(bundle_det3, created_at="2026-05-23T00:00:00")
check("9d. Different inputs → different report_id", report_det1.report_id != report_det3.report_id)


# ---------------------------------------------------------------------------
# Test group 10: Status logic
# ---------------------------------------------------------------------------

print("\n[10] Status logic")

# 10a. Critical feedback → blocked
hrr_10a = _make_human_review_report_blocked("INTC", "run_10a")
bundle_10a = _make_full_input_bundle("INTC", "run_10a", human_review_report=hrr_10a)
rpt_10a = build_reliability_run_report(bundle_10a, created_at="2026-05-23T00:00:00")
check("10a. Critical HR → report status blocked", rpt_10a.status == "blocked")
check("10b. Blocked → approved_for_execution is False", rpt_10a.approved_for_execution is False)
check("10c. Blocked → blocking_reasons populated in summary", len(rpt_10a.summary.blocking_reasons) > 0)

# 10d. Revision request → needs_revision
hrr_10d = _make_human_review_report_revision("MU", "run_10d")
bundle_10d = _make_full_input_bundle("MU", "run_10d", human_review_report=hrr_10d)
rpt_10d = build_reliability_run_report(bundle_10d, created_at="2026-05-23T00:00:00")
check("10d. Revision HR → report status needs_revision", rpt_10d.status == "needs_revision")
check("10e. Revision → revision_reasons populated", len(rpt_10d.summary.revision_reasons) > 0)
check("10f. Revision → no blocking_reasons", len(rpt_10d.summary.blocking_reasons) == 0)

# 10g. Clean approval → complete
hrr_10g = _make_human_review_report_clean("QCOM", "run_10g")
bundle_10g = _make_full_input_bundle("QCOM", "run_10g", human_review_report=hrr_10g)
rpt_10g = build_reliability_run_report(bundle_10g, created_at="2026-05-23T00:00:00")
check("10g. Clean HR → report status complete", rpt_10g.status == "complete")
check("10h. Complete → approved_for_execution still False", rpt_10g.approved_for_execution is False)


# ---------------------------------------------------------------------------
# Test group 11: Missing optional artifacts → warnings without crashing
# ---------------------------------------------------------------------------

print("\n[11] Missing optional artifacts → warnings")

bundle_empty = ReliabilityRunInputBundle(
    bundle_id="b_empty",
    run_id="run_empty",
    as_of="2026-05-23",
    ticker="EMPTY",
)
rpt_empty = build_reliability_run_report(bundle_empty, created_at="2026-05-23T00:00:00")
check("11a. Empty bundle builds without crashing", isinstance(rpt_empty, ReliabilityRunReport))
check("11b. Empty bundle status is unknown", rpt_empty.status == "unknown")
check("11c. Empty bundle has warnings", len(rpt_empty.warnings) > 0)
check("11d. Warning for missing orchestration_report",
      any("orchestration_report" in w for w in rpt_empty.warnings))
check("11e. Warning for missing horizon_synthesis_report",
      any("horizon_synthesis_report" in w for w in rpt_empty.warnings))
check("11f. Warning for missing macro_agent_result",
      any("macro_agent_result" in w for w in rpt_empty.warnings))
check("11g. Warning for missing debate_report",
      any("debate_report" in w for w in rpt_empty.warnings))
check("11h. Warning for missing decision_packet",
      any("decision_packet" in w for w in rpt_empty.warnings))
check("11i. Warning for missing human_review_report",
      any("human_review_report" in w for w in rpt_empty.warnings))

# Partial bundle: only some artifacts present — should not crash
bundle_partial = ReliabilityRunInputBundle(
    bundle_id="b_partial",
    run_id="run_partial",
    as_of="2026-05-23",
    ticker="PART",
    validation_aggregate=_make_validation_aggregate("PART", "run_partial"),
)
rpt_partial = build_reliability_run_report(bundle_partial, created_at="2026-05-23T00:00:00")
check("11j. Partial bundle builds without crashing", isinstance(rpt_partial, ReliabilityRunReport))


# ---------------------------------------------------------------------------
# Test group 12: Inputs are not mutated
# ---------------------------------------------------------------------------

print("\n[12] Input mutation check")

run_id_mut = "run_mut"
ticker_mut = "IBM"
trs_mut = [_make_tool_result(run_id_mut, ticker_mut, i) for i in range(2)]
va_mut = _make_validation_aggregate(ticker_mut, run_id_mut)
bundle_mut = ReliabilityRunInputBundle(
    bundle_id="b_mut",
    run_id=run_id_mut,
    as_of="2026-05-23",
    ticker=ticker_mut,
    tool_results=trs_mut,
    validation_aggregate=va_mut,
)

# Deep copy before
bundle_before = copy.deepcopy(bundle_mut)
_ = build_reliability_run_report(bundle_mut, created_at="2026-05-23T00:00:00")

check("12a. bundle_id not mutated", bundle_mut.bundle_id == bundle_before.bundle_id)
check("12b. run_id not mutated", bundle_mut.run_id == bundle_before.run_id)
check("12c. tool_results not mutated", len(bundle_mut.tool_results) == len(bundle_before.tool_results))
check("12d. validation_aggregate not mutated",
      bundle_mut.validation_aggregate is not None and
      bundle_mut.validation_aggregate.aggregate_id == bundle_before.validation_aggregate.aggregate_id)


# ---------------------------------------------------------------------------
# Test group 13: reliability_run_tool_result_from_report
# ---------------------------------------------------------------------------

print("\n[13] reliability_run_tool_result_from_report")

run_id_tr = "run_tr_test"
bundle_tr = _make_full_input_bundle("CRM", "run_tr_test", include_all=True)
rpt_tr = build_reliability_run_report(bundle_tr, created_at="2026-05-23T00:00:00")
tool_result = reliability_run_tool_result_from_report(
    run_id=run_id_tr,
    report=rpt_tr,
)

check("13a. ToolResult is ToolResult", isinstance(tool_result, ToolResult))
check("13b. tool_name is stable", tool_result.tool_name == _REVIEW_LOOP_TOOL_NAME)
check("13c. target matches report.target", tool_result.inputs.get("target") == rpt_tr.target)
check("13d. evidence_id is non-empty", bool(tool_result.evidence_id))
check("13e. outputs contains report", "report" in tool_result.outputs)
check("13f. outputs contains summary", "summary" in tool_result.outputs)
check("13g. outputs contains calculation_version", "calculation_version" in tool_result.outputs)
check("13h. outputs.calculation_version matches constant",
      tool_result.outputs["calculation_version"] == _CALCULATION_VERSION)
check("13i. outputs.summary.approved_for_execution is False",
      tool_result.outputs["summary"]["approved_for_execution"] is False)

# Deterministic evidence_id
tool_result_2 = reliability_run_tool_result_from_report(run_id=run_id_tr, report=rpt_tr)
check("13j. Deterministic evidence_id", tool_result.evidence_id == tool_result_2.evidence_id)

# Different report → different evidence_id
bundle_tr2 = _make_full_input_bundle("ORCL", "run_tr_test_2", include_all=True)
rpt_tr2 = build_reliability_run_report(bundle_tr2, created_at="2026-05-23T00:00:01")
tool_result_3 = reliability_run_tool_result_from_report(run_id="run_tr_test_2", report=rpt_tr2)
check("13k. Different report → different evidence_id",
      tool_result.evidence_id != tool_result_3.evidence_id)

# Target override
tool_result_target = reliability_run_tool_result_from_report(
    run_id=run_id_tr,
    report=rpt_tr,
    target="override_target",
)
check("13l. Target override respected",
      tool_result_target.inputs.get("target") == "override_target")


# ---------------------------------------------------------------------------
# Test group 14: approved_for_execution always False
# ---------------------------------------------------------------------------

print("\n[14] approved_for_execution always False")

for scenario, bundle_ in [
    ("empty", ReliabilityRunInputBundle(bundle_id="b", run_id="r", as_of="t")),
    ("full",  bundle_full),
    ("blocked", bundle_10a),
    ("revision", bundle_10d),
    ("clean",  bundle_10g),
]:
    rpt_ = build_reliability_run_report(bundle_, created_at="2026-05-23T00:00:00")
    check(f"14. approved_for_execution=False in '{scenario}' scenario",
          rpt_.approved_for_execution is False and
          rpt_.summary.approved_for_execution is False)


# ---------------------------------------------------------------------------
# Test group 15: __all__ exports include Phase 3G symbols
# ---------------------------------------------------------------------------

print("\n[15] __all__ exports")

import lib.reliability as _rel

_expected_3g_symbols = [
    "ReliabilityRunStatus",
    "ReliabilityRunInputBundle",
    "ReliabilityRunSummary",
    "ReliabilityRunReport",
    "make_reliability_run_report_id",
    "determine_reliability_run_status",
    "collect_reliability_run_source_ids",
    "summarize_reliability_run",
    "build_reliability_run_report",
    "reliability_run_tool_result_from_report",
]

for sym in _expected_3g_symbols:
    check(f"15. '{sym}' in __all__", sym in _rel.__all__, f"'{sym}' missing from __all__")
    check(f"15. '{sym}' accessible from lib.reliability", hasattr(_rel, sym),
          f"'{sym}' not importable from lib.reliability")


# ---------------------------------------------------------------------------
# Test group 16: No forbidden module imports
# ---------------------------------------------------------------------------

print("\n[16] No forbidden module imports")

import importlib.util

_forbidden = [
    "streamlit",
    "lib.llm_orchestrator",
    "lib.workflow_state",
]

import lib.reliability.review_loop as _rl_module
_rl_source = open(
    os.path.join(os.path.dirname(__file__), "..", "lib", "reliability", "review_loop.py")
).read()

for mod in _forbidden:
    check(
        f"16. No import of '{mod}' in review_loop.py",
        mod not in _rl_source,
        f"'{mod}' found in review_loop.py source",
    )

# No network calls (no requests/httpx/urllib.request as imports)
import re as _re
_net_import_patterns = [
    (r"\bimport requests\b", "import requests"),
    (r"\bimport httpx\b", "import httpx"),
    (r"\bimport urllib\.request\b", "import urllib.request"),
]
for _pat, _label in _net_import_patterns:
    check(
        f"16. No '{_label}' in review_loop.py",
        not _re.search(_pat, _rl_source),
        f"'{_label}' found in review_loop.py source",
    )


# ---------------------------------------------------------------------------
# Test group 17: Serialization roundtrip
# ---------------------------------------------------------------------------

print("\n[17] Serialization roundtrip")

bundle_ser = _make_full_input_bundle("META", "run_ser", include_all=True)
rpt_ser = build_reliability_run_report(bundle_ser, created_at="2026-05-23T00:00:00")

rpt_dict = rpt_ser.model_dump()
check("17a. model_dump returns dict", isinstance(rpt_dict, dict))
check("17b. report_id in dict", "report_id" in rpt_dict)
check("17c. approved_for_execution in dict", "approved_for_execution" in rpt_dict)
check("17d. approved_for_execution is False in dict", rpt_dict["approved_for_execution"] is False)

# JSON serialization
rpt_json = json.dumps(rpt_dict)
check("17e. JSON serialization succeeds", isinstance(rpt_json, str))
rpt_dict2 = json.loads(rpt_json)
check("17f. JSON roundtrip preserves report_id", rpt_dict2["report_id"] == rpt_ser.report_id)
check("17g. JSON roundtrip preserves status", rpt_dict2["status"] == rpt_ser.status)


# ---------------------------------------------------------------------------
# Test group 18: Status precedence regression — HR revision vs DP fail/blocked
# ---------------------------------------------------------------------------

print("\n[18] Status precedence regression (HR revision vs DP fail/blocked)")

import types as _types

# 18a/18b/18c: HR changes_requested + DP fail → needs_revision
hrr_18a = _make_human_review_report_revision("REGR", "run_18a")
_dp_18a = _types.SimpleNamespace(
    status="fail",
    decision_packet_id="dp_regr_fail_18a",
    recommendation="hold",
    ticker="REGR",
    source_ids={},
)
bundle_18a = ReliabilityRunInputBundle(
    bundle_id="b_18a",
    run_id="run_18a",
    as_of="2026-05-23",
    ticker="REGR",
    human_review_report=hrr_18a,
    decision_packet=_dp_18a,
)

status_18a, br_18a, rr_18a = determine_reliability_run_status(bundle_18a)
check("18a. HR changes_requested + DP fail → needs_revision (status helper)",
      status_18a == "needs_revision",
      f"got {status_18a!r}")

rpt_18a = build_reliability_run_report(bundle_18a, created_at="2026-05-23T00:00:00")
check("18b. HR changes_requested + DP fail → needs_revision (full report)",
      rpt_18a.status == "needs_revision",
      f"got {rpt_18a.status!r}")
check("18c. HR changes_requested + DP fail → approved_for_execution is False",
      rpt_18a.approved_for_execution is False)

# 18d/18e: HR changes_requested + DP blocked → blocked
hrr_18d = _make_human_review_report_revision("REGR", "run_18d")
_dp_18d = _types.SimpleNamespace(
    status="blocked",
    decision_packet_id="dp_regr_blocked_18d",
    recommendation="hold",
    ticker="REGR",
    source_ids={},
)
bundle_18d = ReliabilityRunInputBundle(
    bundle_id="b_18d",
    run_id="run_18d",
    as_of="2026-05-23",
    ticker="REGR",
    human_review_report=hrr_18d,
    decision_packet=_dp_18d,
)

status_18d, br_18d, rr_18d = determine_reliability_run_status(bundle_18d)
check("18d. HR changes_requested + DP blocked → blocked (status helper)",
      status_18d == "blocked",
      f"got {status_18d!r}")

rpt_18d = build_reliability_run_report(bundle_18d, created_at="2026-05-23T00:00:00")
check("18e. HR changes_requested + DP blocked → blocked (full report)",
      rpt_18d.status == "blocked",
      f"got {rpt_18d.status!r}")
check("18f. HR changes_requested + DP blocked → approved_for_execution is False",
      rpt_18d.approved_for_execution is False)


# ---------------------------------------------------------------------------
# Regression: prior Phase 3 test scripts
# ---------------------------------------------------------------------------

print("\n[Regression] Prior Phase 3 test scripts")

_regression_scripts = [
    "scripts/test_reliability_human_review.py",
    "scripts/test_reliability_decision_packet.py",
    "scripts/test_reliability_debate.py",
    "scripts/test_reliability_horizon_synthesis.py",
    "scripts/test_reliability_macro_agent.py",
    "scripts/test_reliability_orchestration_skeleton.py",
    "scripts/test_reliability_phase_2_closeout.py",
]

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for script in _regression_scripts:
    script_path = os.path.join(repo_root, script)
    if not os.path.exists(script_path):
        fail(f"Regression {script}", "script not found")
        continue
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode == 0:
        ok(f"Regression {script}")
    else:
        fail(f"Regression {script}", result.stderr[-300:] if result.stderr else "exit code non-zero")


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  Phase 3G Test Results: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
if _failed_tests:
    print("  Failed tests:")
    for t in _failed_tests:
        print(f"    - {t}")
    sys.exit(1)
else:
    print("  All tests passed.")
    sys.exit(0)
