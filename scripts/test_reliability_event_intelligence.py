"""
scripts/test_reliability_event_intelligence.py

Phase 3R-A: Event Intelligence Agents Skeleton — test suite.

Tests cover:
  - CatalystAssessment construction and validation.
  - NewsImpactAssessment construction and validation.
  - EarningsPlaybookAssessment construction and validation.
  - EstimateRevisionAssessment construction and validation.
  - EventIntelligenceBundle aggregation and empty-list handling.
  - EventIntelligenceSummary construction and enforcement.
  - EventIntelligenceReport construction and enforcement.
  - make_event_intelligence_report_id: deterministic, stable output.
  - make_event_intelligence_bundle_id: deterministic, stable output.
  - determine_event_intelligence_status:
      empty bundle → unknown,
      thesis_changing news → needs_review,
      high-impact catalyst → needs_review,
      risk_escalation trigger → blocked,
      post_earnings_review_required → needs_review,
      high revision magnitude → needs_review,
      clean low-impact bundle → complete.
  - collect_event_intelligence_source_ids: collection, deduplication, order.
  - summarize_event_intelligence: counts, horizons, top_warnings.
  - build_event_intelligence_report: full pipeline, determinism, no mutation.
  - Missing optional event categories produce warnings, not crashes.
  - event_intelligence_tool_result_from_report: tool_name, payload, evidence_id.
  - approved_for_execution is always False throughout.
  - __all__ exports include Phase 3R-A public symbols.
  - No dependency on Streamlit, live LLM, broker/order modules, or network.

Usage:
    python3 scripts/test_reliability_event_intelligence.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import copy
from datetime import datetime, timezone
from typing import Any

import pydantic

from lib.reliability.event_intelligence import (
    _CALCULATION_VERSION,
    _EVENT_INTEL_TOOL_NAME,
    CatalystAssessment,
    EarningsPlaybookAssessment,
    EstimateRevisionAssessment,
    EventIntelligenceBundle,
    EventIntelligenceReport,
    EventIntelligenceSummary,
    NewsImpactAssessment,
    build_event_intelligence_report,
    collect_event_intelligence_source_ids,
    determine_event_intelligence_status,
    event_intelligence_tool_result_from_report,
    make_event_intelligence_bundle_id,
    make_event_intelligence_report_id,
    summarize_event_intelligence,
)
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
    return datetime.now(timezone.utc).isoformat()


_AS_OF = "2026-05-24T12:00:00+00:00"
_RUN_ID = "test_run_phase3ra"
_TICKER = "NVDA"


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def _make_catalyst(
    event_id: str = "cat_001",
    ticker: str = _TICKER,
    magnitude: str = "medium",
    review_trigger: str = "no_review_needed",
    evidence_refs: list[str] | None = None,
    evidence_quality: str = "adequate",
) -> CatalystAssessment:
    return CatalystAssessment(
        event_id=event_id,
        ticker=ticker,
        event_name="Product Launch Q3",
        category="catalyst",
        event_date="2026-06-15",
        affected_horizons=["medium_term"],
        expected_impact_direction="positive",
        expected_impact_magnitude=magnitude,  # type: ignore[arg-type]
        thesis_link="Core growth thesis supported",
        review_trigger=review_trigger,  # type: ignore[arg-type]
        evidence_refs=evidence_refs or ["ev_001"],
        evidence_quality=evidence_quality,  # type: ignore[arg-type]
    )


def _make_news(
    news_id: str = "news_001",
    ticker: str = _TICKER,
    thesis_changing: bool = False,
    impact_magnitude: str = "low",
    review_trigger: str = "no_review_needed",
    evidence_refs: list[str] | None = None,
    evidence_quality: str = "adequate",
) -> NewsImpactAssessment:
    return NewsImpactAssessment(
        news_id=news_id,
        ticker=ticker,
        headline="Company announces record revenue",
        source="Reuters",
        url="https://example.com/article",
        published_at=_AS_OF,
        relevance_level="medium",
        impact_direction="positive",
        impact_magnitude=impact_magnitude,  # type: ignore[arg-type]
        thesis_changing=thesis_changing,
        is_noise=False,
        affected_horizons=["short_term"],
        review_trigger=review_trigger,  # type: ignore[arg-type]
        evidence_refs=evidence_refs or ["ev_002"],
        evidence_quality=evidence_quality,  # type: ignore[arg-type]
    )


def _make_earnings(
    earnings_id: str = "earn_001",
    ticker: str = _TICKER,
    post_review: bool = False,
    review_trigger: str = "no_review_needed",
    evidence_refs: list[str] | None = None,
) -> EarningsPlaybookAssessment:
    return EarningsPlaybookAssessment(
        earnings_id=earnings_id,
        ticker=ticker,
        earnings_date="2026-07-25",
        period="Q2 2026",
        pre_earnings_expectation="Beat expected on EPS",
        key_metrics_to_watch=["EPS", "Revenue", "Data Center Revenue"],
        implied_move=8.5,
        guidance_focus="Forward guidance on data center demand",
        possible_action="wait",
        post_earnings_review_required=post_review,
        affected_horizons=["short_term", "medium_term"],
        review_trigger=review_trigger,  # type: ignore[arg-type]
        evidence_refs=evidence_refs or ["ev_003"],
    )


def _make_revision(
    revision_id: str = "rev_001",
    ticker: str = _TICKER,
    magnitude: str = "medium",
    revision_direction: str = "up",
    review_trigger: str = "no_review_needed",
    evidence_refs: list[str] | None = None,
) -> EstimateRevisionAssessment:
    return EstimateRevisionAssessment(
        revision_id=revision_id,
        ticker=ticker,
        revision_metric="eps",
        revision_direction=revision_direction,  # type: ignore[arg-type]
        revision_magnitude=magnitude,  # type: ignore[arg-type]
        medium_term_impact="Supportive of current thesis",
        valuation_support_or_risk="supports_valuation",
        affected_horizons=["medium_term"],
        review_trigger=review_trigger,  # type: ignore[arg-type]
        evidence_refs=evidence_refs or ["ev_004"],
    )


def _make_bundle(
    target: str = _TICKER,
    catalysts: list[CatalystAssessment] | None = None,
    news: list[NewsImpactAssessment] | None = None,
    earnings: list[EarningsPlaybookAssessment] | None = None,
    revisions: list[EstimateRevisionAssessment] | None = None,
    source_ids: list[str] | None = None,
) -> EventIntelligenceBundle:
    bundle_id = make_event_intelligence_bundle_id(target, _AS_OF)
    return EventIntelligenceBundle(
        bundle_id=bundle_id,
        target=target,
        as_of=_AS_OF,
        catalyst_assessments=catalysts or [],
        news_impact_assessments=news or [],
        earnings_playbooks=earnings or [],
        estimate_revision_assessments=revisions or [],
        source_ids=source_ids or [],
    )


# ---------------------------------------------------------------------------
# Test sections
# ---------------------------------------------------------------------------

def test_catalyst_assessment() -> None:
    print("\n--- CatalystAssessment ---")

    # T01: basic construction
    ca = _make_catalyst()
    check("T01: CatalystAssessment basic construction", ca.event_id == "cat_001")

    # T02: all fields accessible
    check("T02: CatalystAssessment ticker", ca.ticker == _TICKER)
    check("T02b: CatalystAssessment event_name", ca.event_name == "Product Launch Q3")
    check("T02c: CatalystAssessment affected_horizons", "medium_term" in ca.affected_horizons)

    # T03: approved_for_execution defaults False
    check("T03: CatalystAssessment approved_for_execution=False by default", not ca.approved_for_execution)

    # T04: validator rejects approved_for_execution=True
    try:
        CatalystAssessment(
            event_id="bad",
            ticker="AAPL",
            event_name="Bad",
            approved_for_execution=True,
        )
        fail("T04: CatalystAssessment rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T04: CatalystAssessment rejects approved_for_execution=True")

    # T05: whitespace rejection on event_id
    try:
        CatalystAssessment(event_id="   ", ticker="AAPL", event_name="X")
        fail("T05: CatalystAssessment rejects whitespace event_id", "should have raised")
    except pydantic.ValidationError:
        ok("T05: CatalystAssessment rejects whitespace event_id")

    # T06: category field
    check("T06: CatalystAssessment category=catalyst", ca.category == "catalyst")

    # T07: evidence_refs preserved
    check("T07: CatalystAssessment evidence_refs", ca.evidence_refs == ["ev_001"])


def test_news_impact_assessment() -> None:
    print("\n--- NewsImpactAssessment ---")

    ni = _make_news()

    # T10: basic construction
    check("T10: NewsImpactAssessment basic construction", ni.news_id == "news_001")
    check("T10b: NewsImpactAssessment headline", len(ni.headline) > 0)
    check("T10c: NewsImpactAssessment source", ni.source == "Reuters")

    # T11: approved_for_execution defaults False
    check("T11: NewsImpactAssessment approved_for_execution=False", not ni.approved_for_execution)

    # T12: validator rejects approved_for_execution=True
    try:
        NewsImpactAssessment(
            news_id="x", ticker="AAPL", headline="test", source="WSJ",
            approved_for_execution=True,
        )
        fail("T12: NewsImpactAssessment rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T12: NewsImpactAssessment rejects approved_for_execution=True")

    # T13: whitespace rejection on news_id
    try:
        NewsImpactAssessment(news_id="  ", ticker="AAPL", headline="X", source="X")
        fail("T13: NewsImpactAssessment rejects whitespace news_id", "should have raised")
    except pydantic.ValidationError:
        ok("T13: NewsImpactAssessment rejects whitespace news_id")

    # T14: thesis_changing flag
    ni_tc = _make_news(thesis_changing=True)
    check("T14: NewsImpactAssessment thesis_changing=True", ni_tc.thesis_changing)

    # T15: is_noise flag
    check("T15: NewsImpactAssessment is_noise defaults False", not ni.is_noise)


def test_earnings_playbook_assessment() -> None:
    print("\n--- EarningsPlaybookAssessment ---")

    ep = _make_earnings()

    # T20: basic construction
    check("T20: EarningsPlaybookAssessment basic construction", ep.earnings_id == "earn_001")
    check("T20b: EarningsPlaybookAssessment period", ep.period == "Q2 2026")
    check("T20c: EarningsPlaybookAssessment implied_move", ep.implied_move == 8.5)

    # T21: approved_for_execution defaults False
    check("T21: EarningsPlaybookAssessment approved_for_execution=False", not ep.approved_for_execution)

    # T22: validator rejects approved_for_execution=True
    try:
        EarningsPlaybookAssessment(
            earnings_id="x", ticker="AAPL", approved_for_execution=True,
        )
        fail("T22: EarningsPlaybookAssessment rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T22: EarningsPlaybookAssessment rejects approved_for_execution=True")

    # T23: whitespace rejection on earnings_id
    try:
        EarningsPlaybookAssessment(earnings_id="  ", ticker="AAPL")
        fail("T23: EarningsPlaybookAssessment rejects whitespace earnings_id", "should have raised")
    except pydantic.ValidationError:
        ok("T23: EarningsPlaybookAssessment rejects whitespace earnings_id")

    # T24: key_metrics_to_watch
    check("T24: EarningsPlaybookAssessment key_metrics", "EPS" in ep.key_metrics_to_watch)

    # T25: post_earnings_review_required
    ep_pr = _make_earnings(post_review=True)
    check("T25: EarningsPlaybookAssessment post_earnings_review_required=True", ep_pr.post_earnings_review_required)


def test_estimate_revision_assessment() -> None:
    print("\n--- EstimateRevisionAssessment ---")

    er = _make_revision()

    # T30: basic construction
    check("T30: EstimateRevisionAssessment basic construction", er.revision_id == "rev_001")
    check("T30b: EstimateRevisionAssessment revision_metric=eps", er.revision_metric == "eps")
    check("T30c: EstimateRevisionAssessment revision_direction=up", er.revision_direction == "up")

    # T31: approved_for_execution defaults False
    check("T31: EstimateRevisionAssessment approved_for_execution=False", not er.approved_for_execution)

    # T32: validator rejects approved_for_execution=True
    try:
        EstimateRevisionAssessment(
            revision_id="x", ticker="AAPL", approved_for_execution=True,
        )
        fail("T32: EstimateRevisionAssessment rejects approved_for_execution=True", "should have raised")
    except pydantic.ValidationError:
        ok("T32: EstimateRevisionAssessment rejects approved_for_execution=True")

    # T33: whitespace rejection on revision_id
    try:
        EstimateRevisionAssessment(revision_id=" ", ticker="AAPL")
        fail("T33: EstimateRevisionAssessment rejects whitespace revision_id", "should have raised")
    except pydantic.ValidationError:
        ok("T33: EstimateRevisionAssessment rejects whitespace revision_id")

    # T34: valuation_support_or_risk
    check("T34: EstimateRevisionAssessment valuation=supports_valuation", er.valuation_support_or_risk == "supports_valuation")


def test_bundle() -> None:
    print("\n--- EventIntelligenceBundle ---")

    # T40: basic bundle with all four types
    bundle = _make_bundle(
        catalysts=[_make_catalyst()],
        news=[_make_news()],
        earnings=[_make_earnings()],
        revisions=[_make_revision()],
    )
    check("T40: EventIntelligenceBundle basic construction", bundle.target == _TICKER)
    check("T40b: bundle has 1 catalyst", len(bundle.catalyst_assessments) == 1)
    check("T40c: bundle has 1 news", len(bundle.news_impact_assessments) == 1)
    check("T40d: bundle has 1 earnings", len(bundle.earnings_playbooks) == 1)
    check("T40e: bundle has 1 revision", len(bundle.estimate_revision_assessments) == 1)

    # T41: empty bundle (all four absent)
    empty_bundle = _make_bundle()
    check("T41: empty bundle has no catalysts", len(empty_bundle.catalyst_assessments) == 0)
    check("T41b: empty bundle has no news", len(empty_bundle.news_impact_assessments) == 0)

    # T42: whitespace rejection on bundle_id
    try:
        EventIntelligenceBundle(bundle_id="  ", target=_TICKER, as_of=_AS_OF)
        fail("T42: EventIntelligenceBundle rejects whitespace bundle_id", "should have raised")
    except pydantic.ValidationError:
        ok("T42: EventIntelligenceBundle rejects whitespace bundle_id")

    # T43: make_event_intelligence_bundle_id is deterministic
    bid1 = make_event_intelligence_bundle_id(_TICKER, _AS_OF)
    bid2 = make_event_intelligence_bundle_id(_TICKER, _AS_OF)
    check("T43: make_event_intelligence_bundle_id deterministic", bid1 == bid2)
    check("T43b: bundle_id has eib_ prefix", bid1.startswith("eib_"))


def test_status_determination() -> None:
    print("\n--- determine_event_intelligence_status ---")

    # T50: empty bundle → unknown
    empty = _make_bundle()
    check("T50: empty bundle → unknown", determine_event_intelligence_status(empty) == "unknown")

    # T51: thesis_changing news → needs_review
    ni_tc = _make_news(thesis_changing=True)
    bundle_tc = _make_bundle(news=[ni_tc])
    check("T51: thesis_changing news → needs_review",
          determine_event_intelligence_status(bundle_tc) == "needs_review")

    # T52: high-impact catalyst → needs_review
    ca_hi = _make_catalyst(magnitude="high")
    bundle_hi = _make_bundle(catalysts=[ca_hi])
    check("T52: high-impact catalyst → needs_review",
          determine_event_intelligence_status(bundle_hi) == "needs_review")

    # T53: risk_escalation trigger → blocked
    ca_risk = _make_catalyst(review_trigger="risk_escalation")
    bundle_risk = _make_bundle(catalysts=[ca_risk])
    check("T53: risk_escalation catalyst → blocked",
          determine_event_intelligence_status(bundle_risk) == "blocked")

    # T54: risk_escalation on news → blocked
    ni_risk = _make_news(review_trigger="risk_escalation")
    bundle_risk_news = _make_bundle(news=[ni_risk])
    check("T54: risk_escalation news → blocked",
          determine_event_intelligence_status(bundle_risk_news) == "blocked")

    # T55: post_earnings_review_required → needs_review
    ep_pr = _make_earnings(post_review=True)
    bundle_ep = _make_bundle(earnings=[ep_pr])
    check("T55: post_earnings_review_required → needs_review",
          determine_event_intelligence_status(bundle_ep) == "needs_review")

    # T56: high revision magnitude → needs_review
    er_hi = _make_revision(magnitude="high")
    bundle_er = _make_bundle(revisions=[er_hi])
    check("T56: high revision magnitude → needs_review",
          determine_event_intelligence_status(bundle_er) == "needs_review")

    # T57: clean low-impact bundle → complete
    bundle_clean = _make_bundle(
        catalysts=[_make_catalyst(magnitude="low", review_trigger="no_review_needed")],
        news=[_make_news(thesis_changing=False, impact_magnitude="low")],
    )
    check("T57: clean low-impact bundle → complete",
          determine_event_intelligence_status(bundle_clean) == "complete")

    # T58: review_before_event trigger → needs_review
    ca_pre = _make_catalyst(review_trigger="review_before_event")
    bundle_pre = _make_bundle(catalysts=[ca_pre])
    check("T58: review_before_event → needs_review",
          determine_event_intelligence_status(bundle_pre) == "needs_review")

    # T59: blocked takes priority over needs_review
    ca_both = _make_catalyst(magnitude="high", review_trigger="risk_escalation")
    bundle_both = _make_bundle(catalysts=[ca_both])
    check("T59: risk_escalation beats high-impact → blocked",
          determine_event_intelligence_status(bundle_both) == "blocked")

    # T60: only revision category (not high) → complete
    er_low = _make_revision(magnitude="low")
    bundle_er_low = _make_bundle(revisions=[er_low])
    check("T60: low-magnitude revision only → complete",
          determine_event_intelligence_status(bundle_er_low) == "complete")


def test_source_id_collection() -> None:
    print("\n--- collect_event_intelligence_source_ids ---")

    # T65: basic collection
    bundle = _make_bundle(
        catalysts=[_make_catalyst(evidence_refs=["ev_ca"])],
        news=[_make_news(evidence_refs=["ev_ni"])],
        earnings=[_make_earnings(evidence_refs=["ev_ep"])],
        revisions=[_make_revision(evidence_refs=["ev_er"])],
        source_ids=["ev_bundle"],
    )
    ids = collect_event_intelligence_source_ids(bundle)
    check("T65: source IDs include bundle source_ids", "ev_bundle" in ids)
    check("T65b: source IDs include catalyst ref", "ev_ca" in ids)
    check("T65c: source IDs include news ref", "ev_ni" in ids)
    check("T65d: source IDs include earnings ref", "ev_ep" in ids)
    check("T65e: source IDs include revision ref", "ev_er" in ids)
    check("T65f: total 5 unique IDs", len(ids) == 5)

    # T66: deduplication
    bundle_dup = _make_bundle(
        catalysts=[_make_catalyst(evidence_refs=["ev_shared", "ev_cat_only"])],
        news=[_make_news(evidence_refs=["ev_shared", "ev_news_only"])],
        source_ids=["ev_shared"],
    )
    ids_dup = collect_event_intelligence_source_ids(bundle_dup)
    check("T66: deduplicates ev_shared to single entry",
          ids_dup.count("ev_shared") == 1)
    check("T66b: still includes unique refs", "ev_cat_only" in ids_dup and "ev_news_only" in ids_dup)

    # T67: preserves first-occurrence order
    bundle_ord = _make_bundle(
        source_ids=["first_id"],
        catalysts=[_make_catalyst(evidence_refs=["second_id"])],
    )
    ids_ord = collect_event_intelligence_source_ids(bundle_ord)
    check("T67: first_id precedes second_id",
          ids_ord.index("first_id") < ids_ord.index("second_id"))

    # T68: empty bundle → empty list
    empty_bundle = _make_bundle()
    check("T68: empty bundle → empty source IDs", collect_event_intelligence_source_ids(empty_bundle) == [])


def test_summary_builder() -> None:
    print("\n--- summarize_event_intelligence ---")

    bundle = _make_bundle(
        catalysts=[
            _make_catalyst(magnitude="high"),
            _make_catalyst(event_id="cat_002", magnitude="low"),
        ],
        news=[
            _make_news(thesis_changing=True),
            _make_news(news_id="news_002", thesis_changing=False),
        ],
        earnings=[_make_earnings()],
        revisions=[_make_revision()],
    )
    source_ids = collect_event_intelligence_source_ids(bundle)
    status = determine_event_intelligence_status(bundle)
    summary = summarize_event_intelligence(bundle, status, source_ids)

    # T70: counts
    check("T70: catalyst_count=2", summary.catalyst_count == 2)
    check("T70b: news_count=2", summary.news_count == 2)
    check("T70c: earnings_count=1", summary.earnings_count == 1)
    check("T70d: revision_count=1", summary.revision_count == 1)

    # T71: thesis_changing_event_count
    check("T71: thesis_changing_event_count=1", summary.thesis_changing_event_count == 1)

    # T72: high_impact_event_count (1 catalyst with high magnitude)
    check("T72: high_impact_event_count >= 1", summary.high_impact_event_count >= 1)

    # T73: affected_horizons aggregated
    check("T73: affected_horizons includes medium_term", "medium_term" in summary.affected_horizons)
    check("T73b: affected_horizons includes short_term", "short_term" in summary.affected_horizons)

    # T74: approved_for_execution always False
    check("T74: summary approved_for_execution=False", not summary.approved_for_execution)

    # T75: status passed through correctly
    check("T75: summary status matches bundle status", summary.status == status)

    # T76: top_warnings bounded to 5
    bundle_many_warn = _make_bundle(
        catalysts=[
            _make_catalyst(
                event_id=f"cat_{i}",
                evidence_refs=[f"ev_{i}"],
            )
            for i in range(3)
        ],
    )
    # Add warnings to bundle
    bundle_many_warn = EventIntelligenceBundle(
        bundle_id=bundle_many_warn.bundle_id,
        target=bundle_many_warn.target,
        as_of=bundle_many_warn.as_of,
        catalyst_assessments=bundle_many_warn.catalyst_assessments,
        warnings=["w1", "w2", "w3", "w4", "w5", "w6", "w7"],
    )
    s2 = summarize_event_intelligence(
        bundle_many_warn,
        determine_event_intelligence_status(bundle_many_warn),
        collect_event_intelligence_source_ids(bundle_many_warn),
    )
    check("T76: top_warnings capped at 5", len(s2.top_warnings) <= 5)


def test_report_builder() -> None:
    print("\n--- build_event_intelligence_report ---")

    bundle = _make_bundle(
        catalysts=[_make_catalyst()],
        news=[_make_news()],
        earnings=[_make_earnings()],
        revisions=[_make_revision()],
    )

    report = build_event_intelligence_report(bundle, run_id=_RUN_ID, created_at=_AS_OF)

    # T80: report is an EventIntelligenceReport
    check("T80: build returns EventIntelligenceReport", isinstance(report, EventIntelligenceReport))
    check("T80b: report target", report.target == _TICKER)
    check("T80c: report run_id", report.run_id == _RUN_ID)

    # T81: approved_for_execution always False
    check("T81: report approved_for_execution=False", not report.approved_for_execution)
    check("T81b: report summary approved_for_execution=False", not report.summary.approved_for_execution)

    # T82: deterministic report ID
    report2 = build_event_intelligence_report(bundle, run_id=_RUN_ID, created_at=_AS_OF)
    check("T82: deterministic report_id (same inputs)", report.report_id == report2.report_id)

    # T83: report_id has eil_ prefix
    check("T83: report_id has eil_ prefix", report.report_id.startswith("eil_"))

    # T84: calculation_version set
    check("T84: calculation_version set", report.calculation_version == _CALCULATION_VERSION)

    # T85: source_ids populated
    check("T85: source_ids not empty", len(report.source_ids) > 0)

    # T86: inputs not mutated — bundle unchanged after report build
    original_cats = len(bundle.catalyst_assessments)
    _ = build_event_intelligence_report(bundle, run_id=_RUN_ID)
    check("T86: input bundle not mutated", len(bundle.catalyst_assessments) == original_cats)

    # T87: missing optional categories → warnings, not crash
    empty_bundle = _make_bundle()  # all four categories empty
    empty_report = build_event_intelligence_report(empty_bundle, run_id=_RUN_ID, created_at=_AS_OF)
    check("T87: empty bundle builds report without crash",
          isinstance(empty_report, EventIntelligenceReport))
    check("T87b: empty bundle → status unknown", empty_report.status == "unknown")
    check("T87c: empty bundle → warning about no assessments",
          any("no assessments" in w for w in empty_report.warnings))

    # T88: thesis_changing news → needs_review in report
    bundle_tc = _make_bundle(news=[_make_news(thesis_changing=True)])
    report_tc = build_event_intelligence_report(bundle_tc, run_id=_RUN_ID, created_at=_AS_OF)
    check("T88: thesis_changing news → report status needs_review",
          report_tc.status == "needs_review")

    # T89: high-impact catalyst → needs_review in report
    bundle_hi = _make_bundle(catalysts=[_make_catalyst(magnitude="high")])
    report_hi = build_event_intelligence_report(bundle_hi, run_id=_RUN_ID, created_at=_AS_OF)
    check("T89: high-impact catalyst → report status needs_review",
          report_hi.status == "needs_review")

    # T90: high-impact catalyst with unsupported evidence → warning generated
    bundle_evi = _make_bundle(
        catalysts=[_make_catalyst(magnitude="high", evidence_quality="unsupported")]
    )
    report_evi = build_event_intelligence_report(bundle_evi, run_id=_RUN_ID, created_at=_AS_OF)
    check("T90: unsupported evidence on high-impact catalyst → warning",
          any("high-impact" in w for w in report_evi.warnings))

    # T91: risk_escalation → blocked report
    bundle_risk = _make_bundle(catalysts=[_make_catalyst(review_trigger="risk_escalation")])
    report_risk = build_event_intelligence_report(bundle_risk, run_id=_RUN_ID, created_at=_AS_OF)
    check("T91: risk_escalation → report status blocked", report_risk.status == "blocked")


def test_tool_result_adapter() -> None:
    print("\n--- event_intelligence_tool_result_from_report ---")

    bundle = _make_bundle(
        catalysts=[_make_catalyst()],
        news=[_make_news()],
    )
    report = build_event_intelligence_report(bundle, run_id=_RUN_ID, created_at=_AS_OF)
    tr = event_intelligence_tool_result_from_report(
        run_id=_RUN_ID,
        report=report,
    )

    # T95: stable tool_name
    check("T95: tool_name is stable", tr.tool_name == _EVENT_INTEL_TOOL_NAME)
    check("T95b: tool_name == event_intelligence_report", tr.tool_name == "event_intelligence_report")

    # T96: evidence_id is deterministic
    tr2 = event_intelligence_tool_result_from_report(run_id=_RUN_ID, report=report)
    check("T96: evidence_id is deterministic", tr.evidence_id == tr2.evidence_id)

    # T97: outputs contains report, summary, calculation_version
    check("T97: outputs.report present", "report" in tr.outputs)
    check("T97b: outputs.summary present", "summary" in tr.outputs)
    check("T97c: outputs.calculation_version present", "calculation_version" in tr.outputs)

    # T98: approved_for_execution always False in summary payload
    check("T98: summary payload approved_for_execution=False",
          tr.outputs["summary"]["approved_for_execution"] is False)

    # T99: report not mutated by ToolResult wrapping
    check("T99: report approved_for_execution still False after wrap",
          not report.approved_for_execution)

    # T100: run_id propagated
    check("T100: ToolResult run_id matches", tr.run_id == _RUN_ID)


def test_report_id_helpers() -> None:
    print("\n--- ID helper determinism ---")

    # T105: make_event_intelligence_report_id deterministic
    id1 = make_event_intelligence_report_id(_RUN_ID, _TICKER, _AS_OF)
    id2 = make_event_intelligence_report_id(_RUN_ID, _TICKER, _AS_OF)
    check("T105: report_id deterministic", id1 == id2)
    check("T105b: report_id has eil_ prefix", id1.startswith("eil_"))

    # T106: different inputs → different IDs
    id3 = make_event_intelligence_report_id(_RUN_ID, "AAPL", _AS_OF)
    check("T106: different ticker → different report_id", id1 != id3)

    # T107: bundle_id different from report_id
    bid = make_event_intelligence_bundle_id(_TICKER, _AS_OF)
    rid = make_event_intelligence_report_id(_RUN_ID, _TICKER, _AS_OF)
    check("T107: bundle_id != report_id (different prefixes)", bid != rid)
    check("T107b: bundle_id has eib_ prefix", bid.startswith("eib_"))


def test_all_exports() -> None:
    print("\n--- __all__ exports Phase 3R-A symbols ---")

    from lib.reliability import __all__ as exported_all

    phase3ra_symbols = [
        "EventIntelligenceStatus",
        "EventCategory",
        "EventImpactDirection",
        "EventImpactMagnitude",
        "EventReviewTrigger",
        "EventEvidenceQuality",
        "EarningsPlaybookAction",
        "EventRevisionMetric",
        "EventRevisionDirection",
        "EventRevisionValuationImpact",
        "CatalystAssessment",
        "NewsImpactAssessment",
        "EarningsPlaybookAssessment",
        "EstimateRevisionAssessment",
        "EventIntelligenceBundle",
        "EventIntelligenceSummary",
        "EventIntelligenceReport",
        "make_event_intelligence_report_id",
        "make_event_intelligence_bundle_id",
        "determine_event_intelligence_status",
        "collect_event_intelligence_source_ids",
        "summarize_event_intelligence",
        "build_event_intelligence_report",
        "event_intelligence_tool_result_from_report",
    ]

    for sym in phase3ra_symbols:
        check(f"T110: __all__ exports {sym}", sym in exported_all)


def test_no_forbidden_dependencies() -> None:
    print("\n--- No forbidden dependencies ---")

    import lib.reliability.event_intelligence as m
    src = open(os.path.join(os.path.dirname(__file__), "..", "lib", "reliability", "event_intelligence.py")).read()

    check("T120: no streamlit import", "import streamlit" not in src)
    check("T121: no anthropic import", "import anthropic" not in src)
    # Check for import statements specifically (docstring text may mention these words)
    import_lines = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")]
    check("T122: no app.py import", not any("from app" == ln[:8] or ln.startswith("import app") for ln in import_lines))
    check("T123: no broker import", not any("broker" in ln.lower() for ln in import_lines))
    check("T124: no requests/httpx import", "import requests" not in src and "import httpx" not in src)
    check("T125: no yfinance import", "import yfinance" not in src)
    check("T126: no pages import", "from pages" not in src)


def test_summary_validator() -> None:
    print("\n--- EventIntelligenceSummary validator ---")

    # T130: construction with valid data
    s = EventIntelligenceSummary(target=_TICKER, status="complete")
    check("T130: EventIntelligenceSummary valid construction", s.target == _TICKER)

    # T131: rejects approved_for_execution=True
    try:
        EventIntelligenceSummary(target=_TICKER, approved_for_execution=True)
        fail("T131: EventIntelligenceSummary rejects approved_for_execution=True", "should raise")
    except pydantic.ValidationError:
        ok("T131: EventIntelligenceSummary rejects approved_for_execution=True")

    # T132: rejects whitespace target
    try:
        EventIntelligenceSummary(target="  ")
        fail("T132: EventIntelligenceSummary rejects whitespace target", "should raise")
    except pydantic.ValidationError:
        ok("T132: EventIntelligenceSummary rejects whitespace target")


def test_determinism_and_warning_propagation() -> None:
    print("\n--- Determinism (created_at) + warning propagation (Polish fixes) ---")

    # T140: Full report model_dump() is identical for two calls without created_at.
    bundle = _make_bundle(
        catalysts=[_make_catalyst()],
        news=[_make_news()],
    )
    report1 = build_event_intelligence_report(bundle, run_id=_RUN_ID)   # no created_at
    report2 = build_event_intelligence_report(bundle, run_id=_RUN_ID)   # no created_at
    check("T140: model_dump() identical without created_at",
          report1.model_dump() == report2.model_dump())

    # T141: created_at defaults to bundle.as_of (not current time).
    check("T141: created_at defaults to bundle.as_of",
          report1.created_at == bundle.as_of)

    # T141b: explicit created_at override is still respected.
    report_override = build_event_intelligence_report(
        bundle, run_id=_RUN_ID, created_at="2025-01-01T00:00:00Z"
    )
    check("T141b: explicit created_at override respected",
          report_override.created_at == "2025-01-01T00:00:00Z")

    # T141c: ToolResult evidence_id is also deterministic (derives from report dict).
    tr1 = event_intelligence_tool_result_from_report(_RUN_ID, report1)
    tr2 = event_intelligence_tool_result_from_report(_RUN_ID, report2)
    check("T141c: ToolResult evidence_id deterministic without created_at",
          tr1.evidence_id == tr2.evidence_id)

    # T142: High-impact catalyst with unsupported evidence → generated warning
    # appears in BOTH report.warnings AND summary.top_warnings.
    bundle_hi = _make_bundle(
        catalysts=[_make_catalyst(magnitude="high", evidence_quality="unsupported")]
    )
    report_hi = build_event_intelligence_report(bundle_hi, run_id=_RUN_ID)
    check("T142: generated warning in report.warnings",
          any("high-impact" in w for w in report_hi.warnings))
    check("T142b: generated warning in summary.top_warnings",
          any("high-impact" in w for w in report_hi.summary.top_warnings))

    # T143: Thesis-changing news with unsupported evidence → generated warning
    # appears in BOTH report.warnings AND summary.top_warnings.
    bundle_tc = _make_bundle(
        news=[_make_news(thesis_changing=True, evidence_quality="unsupported")]
    )
    report_tc = build_event_intelligence_report(bundle_tc, run_id=_RUN_ID)
    check("T143: thesis-changing unsupported evidence warning in report.warnings",
          any("thesis-changing" in w for w in report_tc.warnings))
    check("T143b: thesis-changing unsupported evidence warning in summary.top_warnings",
          any("thesis-changing" in w for w in report_tc.summary.top_warnings))

    # T144: Warnings are deduplicated — if bundle already contains the same string
    # as a generated warning, it must appear only once in report.warnings and
    # at most once in summary.top_warnings.
    _gen_warn = (
        "CatalystAssessment 'cat_001' is high-impact but "
        "evidence_quality='unsupported'. Manual review required."
    )
    bundle_dup = EventIntelligenceBundle(
        bundle_id=make_event_intelligence_bundle_id(_TICKER, _AS_OF),
        target=_TICKER,
        as_of=_AS_OF,
        catalyst_assessments=[_make_catalyst(magnitude="high", evidence_quality="unsupported")],
        warnings=[_gen_warn],   # pre-existing duplicate of the generated warning
    )
    report_dup = build_event_intelligence_report(bundle_dup, run_id=_RUN_ID)
    check("T144: duplicate report.warnings deduplicated",
          report_dup.warnings.count(_gen_warn) == 1)
    check("T144b: duplicate top_warnings deduplicated",
          report_dup.summary.top_warnings.count(_gen_warn) == 1)

    # T145: Empty bundle → generated warning for "no assessments" appears in
    # both report.warnings and summary.top_warnings.
    empty_bundle = _make_bundle()
    report_empty = build_event_intelligence_report(empty_bundle, run_id=_RUN_ID)
    check("T145: no-assessments warning in report.warnings",
          any("no assessments" in w for w in report_empty.warnings))
    check("T145b: no-assessments warning in summary.top_warnings",
          any("no assessments" in w for w in report_empty.summary.top_warnings))

    # T146: summary.top_warnings deduplication — ensure no duplicates even when
    # bundle.warnings, assessment.warnings, and extra_warnings share entries.
    check("T146: top_warnings has no duplicates",
          len(report_dup.summary.top_warnings) == len(set(report_dup.summary.top_warnings)))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Phase 3R-A: Event Intelligence Agents Skeleton — Test Suite")
    print("=" * 60)

    test_catalyst_assessment()
    test_news_impact_assessment()
    test_earnings_playbook_assessment()
    test_estimate_revision_assessment()
    test_bundle()
    test_status_determination()
    test_source_id_collection()
    test_summary_builder()
    test_report_builder()
    test_tool_result_adapter()
    test_report_id_helpers()
    test_all_exports()
    test_no_forbidden_dependencies()
    test_summary_validator()
    test_determinism_and_warning_propagation()

    print()
    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if _failed_tests:
        print("\nFailed tests:")
        for t in _failed_tests:
            print(f"  {t}")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
